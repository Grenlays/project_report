"""HTTP-сервер сервиса отчётов (стандартная библиотека Python).

Маршруты:
  GET  /                              список проектов (?manager=, ?all=1)
  GET  /projects/<код>                карточка проекта и история отчётов
  POST /projects/<код>/reports        сформировать и сохранить отчёт
  GET  /reports                       архив всех отчётов
  GET  /reports/<id>                  просмотр отчёта
  GET  /reports/<id>/download         отчёт отдельным HTML-файлом
  GET  /reports/<id>.json             отчёт в JSON
Маршрутов изменения и удаления отчётов нет намеренно.

Правки этапов и примечания (редактируемый слой поверх отчёта; в контрольную сумму отчёта не входят,
доступны, пока отчёт не зафиксирован):
  POST /reports/<id>/stages/<этап>/description           свой текст результатов (JSON {"text": ...}; null — исходный)
  POST /reports/<id>/stages/<этап>/remove                убрать этап из отчёта
  POST /reports/<id>/stages/<этап>/restore               вернуть этап
  POST /reports/<id>/lock                                зафиксировать отчёт (форма: locked_by)
  POST /reports/<id>/notes/<этап>                       текст примечания (JSON {"text": ...})
  POST /reports/<id>/notes/<этап>/images                изображение (тело — файл, Content-Type image/*)
  POST /reports/<id>/notes/<этап>/images/<img>/delete   удалить изображение
  GET  /notes/images/<img>                               показать изображение

Резервные копии (делаются и автоматически по расписанию):
  POST /backups                       создать резервную копию сейчас
"""
import json
import logging
import re
import sqlite3
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import backup, config, db, service, templates
from .main_client import MainClient, MainServiceError
from .report_builder import dev_deadline, project_info

log = logging.getLogger("report_service")
CLIENT = MainClient()
SCHEDULER = None  # фоновые резервные копии, запускается в run()
CODE = r"([A-Za-z]+\d+)"


class Handler(BaseHTTPRequestHandler):
    server_version = "ProjectReports/1.0"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    # --- ответы ---
    def _send(self, status, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _error(self, status, msg):
        self._send(status, templates.error_page(msg))

    def _dispatch(self, routes):
        url = urlparse(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        for pattern, fn in routes:
            m = re.fullmatch(pattern, url.path)
            if m:
                conn = db.connect()
                try:
                    return fn(self, conn, query, *m.groups())
                except service.NotFound as ex:
                    return self._error(404, f"Проект {ex} не найден в главном сервисе")
                except _TooLarge:
                    return self._json(413, {"error": "Файл слишком большой (не более "
                                                     f"{config.NOTE_IMAGE_MAX_MB} МБ)"})
                except MainServiceError as ex:
                    return self._error(502, str(ex))
                except sqlite3.IntegrityError as ex:
                    if "зафиксирован" in str(ex):  # правка пришла одновременно с фиксацией
                        return self._json(409, {"error": LOCKED_MSG})
                    raise
                except Exception:
                    log.error(traceback.format_exc())
                    return self._error(500, "Внутренняя ошибка сервиса")
                finally:
                    conn.close()
        self._error(404, "Страница не найдена")

    def do_GET(self):
        self._dispatch(GET_ROUTES)

    def do_POST(self):
        self._dispatch(POST_ROUTES)

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8") if n else ""
        return {k: v[-1].strip() for k, v in parse_qs(raw).items()}

    def _body(self, limit):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise _TooLarge()
        return self.rfile.read(n) if n else b""

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")


class _TooLarge(Exception):
    pass


LOCKED_MSG = "Отчёт зафиксирован — изменить его больше нельзя"


# --- обработчики --------------------------------------------------------------
def h_index(h, conn, q):
    show_all = q.get("all") == "1"
    projects = service.list_projects(CLIENT, conn, show_all=show_all)
    h._send(200, templates.projects_page(projects, show_all, q.get("manager", "")))


def h_project(h, conn, q, code):
    code = code.upper()
    info = project_info(service.find_project(CLIENT, code))
    reports = db.project_reports(conn, code)
    period_start, prev = service.default_period_start(conn, code)
    h._send(200, templates.project_page(info, reports, period_start, prev))


def h_generate(h, conn, q, code):
    code = code.upper()
    form = h._form()
    author = form.get("author", "")
    if not author:
        return h._error(400, "Укажите, кто запрашивает отчёт")
    first_start = None
    if form.get("period_start"):
        try:
            first_start = date.fromisoformat(form["period_start"])
        except ValueError:
            return h._error(400, "Некорректная дата начала периода")
    report_id = service.generate_report(CLIENT, conn, code, author, first_start)
    h._redirect(f"/reports/{report_id}")


def _load(conn, rid):
    rep = db.get_report(conn, int(rid))
    if rep:
        rep["lock"] = db.get_lock(conn, rep["id"])
    return rep


def _live_deadline(rep):
    """Для отчётов, сформированных до появления плитки «Срок завершения разработки»:
    Дата МП из главного сервиса на момент просмотра. Сохранённый отчёт не меняется."""
    if "dev_deadline" in rep["payload"]["project"]:
        return None
    try:
        projects = (CLIENT.roadmap() or {}).get("projects")
    except MainServiceError as ex:
        log.warning("Дата МП для отчёта %s не получена: %s", rep["id"], ex)
        return {"ok": False}
    return {"ok": True, "value": dev_deadline(projects, rep["project_code"]),
            "at": date.today().strftime("%d.%m.%Y")}


def _live_hours(rep):
    """Для отчётов, сформированных до появления раздела «Трудозатраты по проекту»."""
    if "project_hours" in rep["payload"]:
        return None
    try:
        return service.live_project_hours(CLIENT, rep)
    except MainServiceError as ex:
        log.warning("Трудозатраты для отчёта %s не получены: %s", rep["id"], ex)
        return None


def _render(conn, rep, standalone=False, flash=None):
    ok = db.verify(rep)  # проверка целостности — до любых вычислений над отчётом
    if rep["lock"]:  # у зафиксированного отчёта проверяется и слой правок/примечаний
        ok = ok and db.layer_hash(conn, rep["id"]) == rep["lock"]["layer_sha256"]
    notes = db.get_notes(conn, rep["id"], with_data=standalone)
    return templates.report_page(rep, ok, standalone=standalone, live_deadline=_live_deadline(rep),
                                 notes=notes, live_hours=_live_hours(rep),
                                 edits=db.get_edits(conn, rep["id"]), lock=rep["lock"], flash=flash)


def h_report(h, conn, q, rid):
    rep = _load(conn, rid)
    if not rep:
        return h._error(404, "Отчёт не найден")
    h._send(200, _render(conn, rep, flash="locked" if q.get("locked") == "1" and rep["lock"] else None))


def h_report_download(h, conn, q, rid):
    rep = _load(conn, rid)
    if not rep:
        return h._error(404, "Отчёт не найден")
    name = f'report_{rep["project_code"]}_{rep["created_at"][:10]}_{rep["id"]}.html'
    h._send(200, _render(conn, rep, standalone=True),
            headers={"Content-Disposition": f'attachment; filename="{name}"'})


def h_report_json(h, conn, q, rid):
    rep = _load(conn, rid)
    if not rep:
        return h._error(404, "Отчёт не найден")
    notes = {vid: {"text": n["text"], "updated_at": n["updated_at"],
                   "images": [f'/notes/images/{i["id"]}' for i in n["images"]]}
             for vid, n in db.get_notes(conn, rep["id"]).items()}
    h._send(200, json.dumps({**rep, "stage_notes": notes, "stage_edits": db.get_edits(conn, rep["id"])},
                            ensure_ascii=False, indent=2),
            "application/json; charset=utf-8")


# --- примечания к этапам -------------------------------------------------------
IMAGE_SIGNATURES = [(b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
                    (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif")]


def _image_mime(data: bytes):
    """Тип изображения по содержимому (SVG и прочее не принимаются)."""
    for sig, mime in IMAGE_SIGNATURES:
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _note_target(h, conn, rid, vid):
    """Проверяет, что отчёт существует, не зафиксирован и этап в нём есть."""
    rep = _load(conn, rid)
    if not rep:
        h._json(404, {"error": "Отчёт не найден"})
        return None
    if rep["lock"]:
        h._json(409, {"error": LOCKED_MSG})
        return None
    p = rep["payload"]
    if vid not in {s["version_id"] for s in p["current_stages"] + p["closed_stages"]}:
        h._json(404, {"error": "Этап не найден в отчёте"})
        return None
    return rep


def h_note_text(h, conn, q, rid, vid):
    if not _note_target(h, conn, rid, vid):
        return
    try:
        text = str(json.loads(h._body(config.NOTE_TEXT_MAX * 4) or b"{}").get("text") or "")
    except (ValueError, AttributeError):
        return h._json(400, {"error": "Некорректный запрос"})
    if len(text) > config.NOTE_TEXT_MAX:
        return h._json(400, {"error": f"Примечание длиннее {config.NOTE_TEXT_MAX} символов"})
    db.set_note_text(conn, int(rid), vid, text.strip())
    h._json(200, {"ok": True})


def h_note_image_add(h, conn, q, rid, vid):
    if not _note_target(h, conn, rid, vid):
        return
    data = h._body(config.NOTE_IMAGE_MAX_MB * 1024 * 1024)
    mime = _image_mime(data)
    if not mime:
        return h._json(400, {"error": "Поддерживаются изображения PNG, JPEG, GIF и WebP"})
    img_id = db.add_note_image(conn, int(rid), vid, mime, data)
    h._json(200, {"id": img_id, "url": f"/notes/images/{img_id}"})


def h_note_image_delete(h, conn, q, rid, vid, img):
    if not _note_target(h, conn, rid, vid):
        return
    if not db.delete_note_image(conn, int(rid), vid, int(img)):
        return h._json(404, {"error": "Изображение не найдено"})
    h._json(200, {"ok": True})


def _read_text(h):
    """Текст из JSON-тела {"text": ...}; None в "text" — вернуть исходное значение."""
    try:
        obj = json.loads(h._body(config.NOTE_TEXT_MAX * 4) or b"{}")
        text = obj.get("text")
    except (ValueError, AttributeError):
        raise ValueError("Некорректный запрос")
    if text is None:
        return None
    text = str(text).strip()
    if len(text) > config.NOTE_TEXT_MAX:
        raise ValueError(f"Текст длиннее {config.NOTE_TEXT_MAX} символов")
    return text


def h_stage_description(h, conn, q, rid, vid):
    if not _note_target(h, conn, rid, vid):
        return
    try:
        text = _read_text(h)
    except ValueError as ex:
        return h._json(400, {"error": str(ex)})
    db.set_stage_description(conn, int(rid), vid, text)
    h._json(200, {"ok": True})


def h_stage_remove(h, conn, q, rid, vid, removed=True):
    h._body(1024)  # дочитать тело запроса
    if not _note_target(h, conn, rid, vid):
        return
    db.set_stage_removed(conn, int(rid), vid, removed)
    h._json(200, {"ok": True})


def h_stage_restore(h, conn, q, rid, vid):
    h_stage_remove(h, conn, q, rid, vid, removed=False)


def h_lock(h, conn, q, rid):
    form = h._form()
    rep = _load(conn, rid)
    if not rep:
        return h._error(404, "Отчёт не найден")
    who = form.get("locked_by", "")[:200]
    if not who:
        return h._error(400, "Укажите, кто фиксирует отчёт")
    if not rep["lock"]:
        db.lock_report(conn, rep["id"], who)
        log.info("Отчёт %s зафиксирован (%s)", rep["id"], who)
    h._redirect(f"/reports/{rep['id']}?locked=1")


def h_note_image(h, conn, q, img):
    row = db.get_note_image(conn, int(img))
    if not row:
        return h._error(404, "Изображение не найдено")
    h._send(200, bytes(row["data"]), row["mime"],
            headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


def _backup_status(flash=None):
    items = backup.list_backups()
    return {"last": items[0] if items else None, "count": len(items), "dir": str(config.BACKUP_DIR),
            "interval": config.BACKUP_INTERVAL_HOURS, "keep": config.BACKUP_KEEP,
            "error": SCHEDULER.last_error if SCHEDULER else None, "flash": flash}


def h_reports(h, conn, q):
    project = (q.get("project") or "").upper()
    flash = {"ok": "Резервная копия создана", "err": "Не удалось создать резервную копию — см. журнал сервиса"}
    h._send(200, templates.reports_page(db.all_reports(conn, project or None),
                                        db.archived_projects(conn), project,
                                        backup=_backup_status(flash.get(q.get("backup")))))


def h_backup_now(h, conn, q):
    h._form()  # дочитать тело запроса
    try:
        backup.make_backup()
        h._redirect("/reports?backup=ok")
    except Exception as ex:
        log.error("Ручная резервная копия не создана: %s", ex)
        h._redirect("/reports?backup=err")


GET_ROUTES = [
    (r"/", h_index),
    (rf"/projects/{CODE}", h_project),
    (r"/reports", h_reports),
    (r"/reports/(\d+)", h_report),
    (r"/reports/(\d+)/download", h_report_download),
    (r"/reports/(\d+)\.json", h_report_json),
    (r"/notes/images/(\d+)", h_note_image),
]
STAGE = r"([\w-]+)"
POST_ROUTES = [
    (rf"/projects/{CODE}/reports", h_generate),
    (rf"/reports/(\d+)/notes/{STAGE}", h_note_text),
    (rf"/reports/(\d+)/notes/{STAGE}/images", h_note_image_add),
    (rf"/reports/(\d+)/notes/{STAGE}/images/(\d+)/delete", h_note_image_delete),
    (rf"/reports/(\d+)/stages/{STAGE}/description", h_stage_description),
    (rf"/reports/(\d+)/stages/{STAGE}/remove", h_stage_remove),
    (rf"/reports/(\d+)/stages/{STAGE}/restore", h_stage_restore),
    (r"/reports/(\d+)/lock", h_lock),
    (r"/backups", h_backup_now),
]


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.connect().close()
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    log.info("Сервис отчётов: http://%s:%s  (главный сервис: %s, БД: %s)",
             config.HOST, config.PORT, config.MAIN_URL, config.DB_PATH)
    global SCHEDULER
    SCHEDULER = backup.BackupScheduler()
    SCHEDULER.start()
    log.info("Резервные копии: %s, каждые %s ч, хранить %s шт.",
             config.BACKUP_DIR, config.BACKUP_INTERVAL_HOURS, config.BACKUP_KEEP)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
