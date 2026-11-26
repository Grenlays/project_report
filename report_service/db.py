"""Хранилище отчётов (SQLite).

Пока отчёт не зафиксирован (черновик), его содержимое можно пересобрать по актуальным данным
главного сервиса (update_report_payload) и удалить (delete_draft_report). После фиксации
(report_locks) триггеры БД запрещают и UPDATE, и DELETE, а сама фиксация неизменяема.

Поверх отчёта есть редактируемый слой — правки этапов (stage_edits: изменённый текст
результатов, удаление этапа из списка) и примечания (stage_notes, note_images; ключ — этап или
сводная группа подразделения `grp:<раздел>:<подразделение>`). Слой можно править, пока отчёт
не зафиксирован. После фиксации триггеры БД запрещают любые изменения слоя; контрольная сумма
слоя сохраняется в момент фиксации.
"""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_code  TEXT NOT NULL,          -- J028
    project_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL,          -- дата и время проведения отчёта (ISO, локальное время)
    period_start  TEXT NOT NULL,          -- начало отчётного периода (дата предыдущего отчёта)
    previous_id   INTEGER REFERENCES reports(id),
    author        TEXT NOT NULL,          -- кто запросил отчёт
    payload       TEXT NOT NULL,          -- содержимое отчёта + снимок исходных данных (JSON)
    payload_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_project ON reports(project_code, created_at);

-- Примечания к этапам и сводным группам отчёта. В отличие от самих отчётов их можно править в любое время;
-- в содержимое и контрольную сумму отчёта они не входят.
CREATE TABLE IF NOT EXISTS stage_notes (
    report_id   INTEGER NOT NULL REFERENCES reports(id),
    version_id  TEXT NOT NULL,
    text        TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (report_id, version_id)
);
CREATE TABLE IF NOT EXISTS note_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL REFERENCES reports(id),
    version_id  TEXT NOT NULL,
    mime        TEXT NOT NULL,
    data        BLOB NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_note_images ON note_images(report_id, version_id);

-- Правки этапов: свой текст результатов (NULL — как в главном сервисе) и удаление этапа из отчёта.
CREATE TABLE IF NOT EXISTS stage_edits (
    report_id   INTEGER NOT NULL REFERENCES reports(id),
    version_id  TEXT NOT NULL,
    description TEXT,
    removed     INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (report_id, version_id)
);

-- Фиксация отчёта: после неё правки этапов и примечания изменить нельзя.
CREATE TABLE IF NOT EXISTS report_locks (
    report_id   INTEGER PRIMARY KEY REFERENCES reports(id),
    locked_at   TEXT NOT NULL,
    locked_by   TEXT NOT NULL,
    layer_sha256 TEXT NOT NULL            -- контрольная сумма правок и примечаний на момент фиксации
);
CREATE TRIGGER IF NOT EXISTS report_locks_no_update BEFORE UPDATE ON report_locks
BEGIN SELECT RAISE(ABORT, 'Фиксацию отчёта нельзя изменить'); END;
CREATE TRIGGER IF NOT EXISTS report_locks_no_delete BEFORE DELETE ON report_locks
BEGIN SELECT RAISE(ABORT, 'Фиксацию отчёта нельзя отменить'); END;

-- Черновик (незафиксированный отчёт) можно пересобрать по актуальным данным и удалить;
-- зафиксированный отчёт не меняется и не удаляется. Старые триггеры полного запрета удаляются,
-- чтобы уже существующие базы перешли на новое правило.
DROP TRIGGER IF EXISTS reports_no_update;
DROP TRIGGER IF EXISTS reports_no_delete;
CREATE TRIGGER IF NOT EXISTS reports_locked_no_update BEFORE UPDATE ON reports
WHEN EXISTS (SELECT 1 FROM report_locks WHERE report_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'Отчёт зафиксирован'); END;
CREATE TRIGGER IF NOT EXISTS reports_locked_no_delete BEFORE DELETE ON reports
WHEN EXISTS (SELECT 1 FROM report_locks WHERE report_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'Отчёт зафиксирован'); END;
"""

# Запрет изменений редактируемого слоя зафиксированного отчёта (на уровне БД).
for _t in ("stage_notes", "note_images", "stage_edits"):
    for _op, _row in (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD")):
        SCHEMA += (f"CREATE TRIGGER IF NOT EXISTS {_t}_locked_{_op.lower()} BEFORE {_op} ON {_t}"
                   f" WHEN EXISTS (SELECT 1 FROM report_locks WHERE report_id = {_row}.report_id)"
                   f" BEGIN SELECT RAISE(ABORT, 'Отчёт зафиксирован'); END;\n")



def connect(path: Path = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row(r):
    if r is None:
        return None
    d = dict(r)
    d["payload"] = json.loads(d["payload"])
    return d


def _payload_json(payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def insert_report(conn, *, project_code, project_name, created_at, period_start,
                  previous_id, author, payload) -> int:
    text, sha = _payload_json(payload)
    with conn:
        cur = conn.execute(
            "INSERT INTO reports(project_code, project_name, created_at, period_start, previous_id,"
            " author, payload, payload_sha256) VALUES (?,?,?,?,?,?,?,?)",
            (project_code, project_name, created_at, period_start, previous_id, author, text, sha),
        )
    return cur.lastrowid


def update_report_payload(conn, report_id: int, payload) -> bool:
    """Пересобирает содержимое отчёта (для черновика) и пересчитывает контрольную сумму.

    Дата проведения, период, автор и ссылка на предыдущий отчёт остаются прежними —
    они входят в payload, поэтому вызывающий код обязан сохранить их в новом payload.
    Название проекта обновляется вместе с содержимым (проект могли переименовать).
    Для зафиксированного отчёта триггер БД поднимет IntegrityError('Отчёт зафиксирован').
    """
    text, sha = _payload_json(payload)
    name = ((payload.get("project") or {}).get("name") or "").strip()
    with conn:
        cur = conn.execute(
            "UPDATE reports SET payload=?, payload_sha256=?,"
            " project_name=COALESCE(NULLIF(?, ''), project_name) WHERE id=?",
            (text, sha, name, report_id))
    return cur.rowcount > 0


def delete_draft_report(conn, report_id: int) -> bool:
    """Удаляет черновик отчёта вместе с примечаниями и правками этапов.

    Зафиксированный отчёт удалить нельзя: поднимается sqlite3.IntegrityError.
    """
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if get_lock(conn, report_id):
            raise sqlite3.IntegrityError("Отчёт зафиксирован")
        for table in ("note_images", "stage_notes", "stage_edits"):
            conn.execute(f"DELETE FROM {table} WHERE report_id=?", (report_id,))
        cur = conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
    return cur.rowcount > 0


def get_report(conn, report_id: int):
    return _row(conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())


def last_report(conn, project_code: str):
    return _row(conn.execute(
        "SELECT * FROM reports WHERE project_code=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (project_code,)).fetchone())


def project_reports(conn, project_code: str, with_payload=False):
    rows = conn.execute(
        "SELECT r.*, l.locked_at, l.locked_by FROM reports r LEFT JOIN report_locks l ON l.report_id = r.id"
        " WHERE project_code=? ORDER BY created_at ASC, r.id ASC", (project_code,)).fetchall()
    if with_payload:
        return [_row(r) for r in rows]
    return [{k: r[k] for k in r.keys() if k != "payload"} for r in rows]


def all_reports(conn, project_code=None, limit=500):
    where, args = ("WHERE project_code=?", [project_code]) if project_code else ("", [])
    rows = conn.execute(
        "SELECT r.id, project_code, project_name, created_at, period_start, author, payload_sha256,"
        " l.locked_at, l.locked_by FROM reports r LEFT JOIN report_locks l ON l.report_id = r.id"
        f" {where} ORDER BY created_at DESC, r.id DESC LIMIT ?", (*args, limit)).fetchall()
    return [dict(r) for r in rows]


def archived_projects(conn):
    """Проекты, по которым есть отчёты: [(код, название последнего отчёта, кол-во)]."""
    rows = conn.execute(
        "SELECT project_code, COUNT(*) AS cnt,"
        " (SELECT project_name FROM reports x WHERE x.project_code = r.project_code"
        "  ORDER BY id DESC LIMIT 1) AS name"
        " FROM reports r GROUP BY project_code ORDER BY project_code").fetchall()
    return [(r["project_code"], r["name"], r["cnt"]) for r in rows]


def last_report_dates(conn):
    rows = conn.execute(
        "SELECT project_code, MAX(created_at) AS last, COUNT(*) AS cnt FROM reports GROUP BY project_code")
    return {r["project_code"]: (r["last"], r["cnt"]) for r in rows}


# --- примечания к этапам -----------------------------------------------------
def _now():
    return datetime.now().replace(microsecond=0).isoformat()


def get_notes(conn, report_id: int, with_data=False):
    """{version_id: {"text", "updated_at", "images": [{"id", "mime", ["data"]}]}}"""
    out = {}
    for r in conn.execute("SELECT version_id, text, updated_at FROM stage_notes WHERE report_id=?", (report_id,)):
        out[r["version_id"]] = {"text": r["text"], "updated_at": r["updated_at"], "images": []}
    cols = "id, version_id, mime, created_at" + (", data" if with_data else "")
    for r in conn.execute(f"SELECT {cols} FROM note_images WHERE report_id=? ORDER BY id", (report_id,)):
        n = out.setdefault(r["version_id"], {"text": "", "updated_at": r["created_at"], "images": []})
        img = {"id": r["id"], "mime": r["mime"]}
        if with_data:
            img["data"] = bytes(r["data"])
        n["images"].append(img)
        n["updated_at"] = max(n["updated_at"], r["created_at"])
    return out


def set_note_text(conn, report_id: int, version_id: str, text: str):
    with conn:
        conn.execute(
            "INSERT INTO stage_notes(report_id, version_id, text, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(report_id, version_id) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at",
            (report_id, version_id, text, _now()))


def add_note_image(conn, report_id: int, version_id: str, mime: str, data: bytes) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO note_images(report_id, version_id, mime, data, created_at) VALUES (?,?,?,?,?)",
            (report_id, version_id, mime, data, _now()))
    return cur.lastrowid


def get_note_image(conn, image_id: int):
    r = conn.execute("SELECT id, report_id, version_id, mime, data FROM note_images WHERE id=?",
                     (image_id,)).fetchone()
    return dict(r) if r else None


def delete_note_image(conn, report_id: int, version_id: str, image_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM note_images WHERE id=? AND report_id=? AND version_id=?",
                           (image_id, report_id, version_id))
    return cur.rowcount > 0


# --- правки этапов -------------------------------------------------------------
def get_edits(conn, report_id: int):
    """{version_id: {"description": str | None, "removed": bool, "updated_at"}}"""
    return {r["version_id"]: {"description": r["description"], "removed": bool(r["removed"]),
                              "updated_at": r["updated_at"]}
            for r in conn.execute("SELECT * FROM stage_edits WHERE report_id=?", (report_id,))}


def _upsert_edit(conn, report_id, version_id, column, value):
    with conn:
        conn.execute(
            f"INSERT INTO stage_edits(report_id, version_id, {column}, updated_at) VALUES (?,?,?,?)"
            f" ON CONFLICT(report_id, version_id) DO UPDATE SET {column}=excluded.{column},"
            " updated_at=excluded.updated_at", (report_id, version_id, value, _now()))


def set_stage_description(conn, report_id: int, version_id: str, text):
    """text=None — вернуть текст результатов из главного сервиса."""
    _upsert_edit(conn, report_id, version_id, "description", text)


def set_stage_removed(conn, report_id: int, version_id: str, removed: bool):
    _upsert_edit(conn, report_id, version_id, "removed", 1 if removed else 0)


# --- фиксация ----------------------------------------------------------------
def layer_hash(conn, report_id: int) -> str:
    """Контрольная сумма редактируемого слоя: правки этапов, тексты примечаний, изображения."""
    edits = {k: {"description": v["description"], "removed": v["removed"]}
             for k, v in get_edits(conn, report_id).items()}
    notes = {vid: {"text": n["text"], "images": [hashlib.sha256(i["data"]).hexdigest() for i in n["images"]]}
             for vid, n in get_notes(conn, report_id, with_data=True).items()}
    text = json.dumps({"edits": edits, "notes": notes}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_lock(conn, report_id: int):
    r = conn.execute("SELECT * FROM report_locks WHERE report_id=?", (report_id,)).fetchone()
    return dict(r) if r else None


def lock_report(conn, report_id: int, locked_by: str):
    """Фиксирует отчёт. Возвращает запись фиксации; повторная фиксация ничего не меняет."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")  # чтобы между подсчётом суммы и фиксацией никто не успел внести правку
        if not get_lock(conn, report_id):
            conn.execute("INSERT INTO report_locks(report_id, locked_at, locked_by, layer_sha256) VALUES (?,?,?,?)",
                         (report_id, _now(), locked_by, layer_hash(conn, report_id)))
    return get_lock(conn, report_id)


def verify(report) -> bool:
    text = json.dumps(report["payload"], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() == report["payload_sha256"]
