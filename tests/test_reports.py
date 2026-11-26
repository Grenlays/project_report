import re
import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from report_service import db, service, templates
from report_service.main_client import MainClient, MainServiceError
from report_service.report_builder import build_milestones, project_code, select_stages


def ms(name, m, y, comment=""):
    return {"project": "J028_X", "name": name, "month": m, "year": y, "comment": comment}


def st(vid, closed, planned, last=None):
    return {"version_id": vid, "project_name": "J028_X", "version_name": f"Этап {vid}", "planned_date": planned,
            "is_closed": closed, "description": "Результат", "last_hours_date": last, "manager": "Иванов И.И."}


ROADMAP_J028 = {"key": "J028", "mp_date": "2027-01-01", "mp_date_by": "Горский С.Ю.",
                "end_status": "fixed", "end_status_date": "2026-12-01", "end_status_by": "Рыжов Александр",
                "end_status_at": "2026-11-05", "dev_done": False, "dev_done_date": None}


class FakeClient:
    def __init__(self):
        self.milestones_data = [ms("Опытный образец", 10, 2026), ms("Постановка", 12, 2026)]
        self.stages_data = [st("1", False, "2026-11-30"), st("2", True, "2026-11-01", "2026-11-02"),
                            st("3", True, "2025-01-01", "2025-01-05")]
        self.status_data = [{"ID проекта": "J_028", "Наименование проекта": "X",
                             "Направление проекта": "Магнитная стимуляция", "Тип проекта": "Разработка изделия",
                             "Статус проекта": "Разработка", "Менеджер проекта": "Горский С.Ю."}]

    def project_statuses(self):
        return self.status_data

    def milestones(self):
        return self.milestones_data

    def stages(self):
        return self.stages_data

    def roadmap(self):
        return {"projects": [ROADMAP_J028]}

    def filters(self):
        return {"projects": ["J028_X"], "subdivision_map": {"Петров": "КО", "Сидоров": "ОРПО"},
                "subdivision_color_map": {"КО": "#52c41a"}}

    def project_detail(self, name):
        w = lambda *pairs: {m: {"hours": h} for m, h in pairs}
        return {"short_name": name, "versions": [
            {"version_id": "1", "users": [
                {"name": "Петров", "total_hours": 30, "weekly_hours": w(("2026-09-07", 10), ("2026-10-05", 20))},
                {"name": "Сидоров", "total_hours": 5, "weekly_hours": w(("2026-10-12", 5))},
                {"name": "Неизвестный", "total_hours": 1, "weekly_hours": w(("2026-08-03", 1))}]},
            {"version_id": None, "users": [{"name": "Петров", "total_hours": 99, "weekly_hours": {}}]}]}

    def stage_date_changes(self, vid):
        return [{"old_date": "2026-10-15", "new_date": "2026-11-30", "changed_at": "2026-11-10T06:53:39"}] if vid == "1" else []


class BuilderTests(unittest.TestCase):
    def test_project_code(self):
        self.assertEqual(project_code("J_028"), "J028")
        self.assertEqual(project_code("J028_Портативный стимулятор MSP"), "J028")
        self.assertIsNone(project_code("(без кода) проект"))

    def test_first_report_milestones(self):
        up, closed, _ = build_milestones([ms("A", 10, 2026), ms("B", 11, 2026), ms("C", 1, 2026)],
                                         [], date(2026, 11, 13), date(2026, 10, 14))
        self.assertEqual([m["name"] for m in up], ["B"])  # текущий месяц — актуальная точка
        self.assertEqual([m["name"] for m in closed], ["A"])  # C — до начала периода
        self.assertEqual(closed[0]["deviation_months"], 0)

    def test_closed_milestone_plan_vs_fact(self):
        first = {"created_at": "2026-09-01T10:00:00",
                 "snapshot": {"milestones": {"A|": {"name": "A", "comment": "", "year": 2026, "month": 9}}, "stages": {}}}
        # точку перенесли на октябрь и она прошла
        up, closed, _ = build_milestones([ms("A", 10, 2026)], [first], date(2026, 11, 13), date(2026, 9, 1))
        self.assertEqual(up, [])
        self.assertEqual(closed[0]["plan_label"], "сентябрь 2026")
        self.assertEqual(closed[0]["fact_label"], "октябрь 2026")
        self.assertEqual(closed[0]["deviation_months"], 1)

    def test_milestone_closed_before_prev_report_not_repeated(self):
        prev = {"created_at": "2026-11-01T10:00:00",
                "snapshot": {"milestones": {"A|": {"name": "A", "comment": "", "year": 2026, "month": 10}}, "stages": {}}}
        _, closed, _ = build_milestones([ms("A", 10, 2026)], [prev], date(2026, 11, 13), date(2026, 11, 1))
        self.assertEqual(closed, [])

    def test_project_hours_cutoff(self):
        from report_service.report_builder import project_hours
        w = lambda *pairs: {m: {"hours": h} for m, h in pairs}
        details = [{"versions": [
            {"version_id": "1", "users": [{"name": "A", "weekly_hours": w(("2026-10-05", 10), ("2026-11-16", 7))}]},
            {"version_id": None, "users": [{"name": "B", "weekly_hours": w(("2026-09-07", 4), ("2026-10-12", 6))}]}]}]
        ph = project_hours(details, {"A": "КО", "B": "ОТ"}, date(2026, 10, 10), date(2026, 11, 13))
        # неделя 16.11 позже даты отчёта — не учитывается; списания вне этапов (B) — учитываются
        self.assertEqual((ph["total"], ph["period"], ph["since"]), (20.0, 6.0, "2026-09-07"))
        self.assertEqual([(r["subdivision"], r["total"], r["period"]) for r in ph["by_subdivision"]],
                         [("КО", 10.0, 0.0), ("ОТ", 10.0, 6.0)])

    def test_stages_since_previous(self):
        prev = {"created_at": "2026-10-01T10:00:00", "snapshot": {"milestones": {}, "stages": {
            "2": {"version_id": "2", "is_closed": False, "planned_date": "2026-10-20"},
            "3": {"version_id": "3", "is_closed": True, "planned_date": "2025-01-01"}}}}
        current, closed, _ = select_stages(FakeClient().stages_data, [prev], date(2026, 10, 1))
        self.assertEqual([s["version_id"] for s in current], ["1"])
        self.assertEqual([s["version_id"] for s in closed], ["2"])


class GroupingTests(unittest.TestCase):
    def test_group_by_subdivision(self):
        st = [{"name": "a", "subdivision": "ОРЭО"}, {"name": "b", "subdivision": ""},
              {"name": "c", "subdivision": "КО"}, {"name": "d", "subdivision": "ОРЭО"}]
        g = templates.group_by_subdivision(st)
        self.assertEqual([(k, [s["name"] for s in v]) for k, v in g],
                         [("КО", ["c"]), ("ОРЭО", ["a", "d"]), (templates.NO_SUBDIVISION, ["b"])])


class ElapsedTests(unittest.TestCase):
    def test_elapsed(self):
        from report_service.templates import elapsed
        self.assertEqual(elapsed(date(2021, 7, 1), date(2026, 11, 13)), "5 лет 4 месяца 12 дней")
        self.assertEqual(elapsed(date(2022, 8, 1), date(2026, 11, 13)), "4 года 3 месяца 12 дней")
        self.assertEqual(elapsed(date(2025, 11, 13), date(2026, 11, 13)), "1 год")
        self.assertEqual(elapsed(date(2026, 1, 31), date(2026, 3, 1)), "1 месяц 1 день")
        self.assertEqual(elapsed(date(2026, 11, 13), date(2026, 11, 13)), "0 дней")
        self.assertEqual(elapsed(date(2026, 10, 20), date(2026, 11, 13)), "24 дня")

    def test_date_tiles(self):
        from report_service.templates import _date_tile
        html = _date_tile("#000", "С открытия проекта", "01.07.2021", "2026-11-13")
        self.assertIn('<div class="v">5 лет 4 месяца 12 дней</div>', html)
        self.assertIn("с 01.07.2021", html)
        self.assertIn("не указана", _date_tile("#000", "С начала работ", None, "2026-11-13"))

    def test_dev_deadline(self):
        from report_service.report_builder import dev_deadline
        dl = dev_deadline([ROADMAP_J028], "J028")
        from report_service.report_builder import deadline_pick
        # плановая (fixed) и Дата МП
        self.assertEqual([(d["label"], d["month"]) for d in dl["dates"]],
                         [("Планируемая дата", "2026-12"), ("Дата МП", "2027-01")])
        self.assertEqual(deadline_pick(dl["dates"]), ("2027-01", ["Дата МП"]))
        self.assertFalse(dl["dev_done"])
        # проект из двух частей — по каждому виду самая поздняя дата, срок — самая дальняя из них
        parts = [{"key": "J090", "mp_date": "2028-02-01", "end_status": "desired", "end_status_date": "2028-03-01"},
                 {"key": "J090#2", "mp_date": "2029-02-01", "end_status": "desired", "end_status_date": "2029-12-01"}]
        dl = dev_deadline(parts, "J090")
        self.assertEqual([(d["kind"], d["month"]) for d in dl["dates"]], [("mp", "2029-02"), ("desired", "2029-12")])
        self.assertEqual(deadline_pick(dl["dates"]), ("2029-12", ["Желаемая дата"]))
        # совпадающие даты — указываются обе
        same = dev_deadline([{"key": "J1", "mp_date": "2027-06-01", "end_status": "desired",
                              "end_status_date": "2027-06-01"}], "J1")
        self.assertEqual(deadline_pick(same["dates"]), ("2027-06", ["Дата МП", "Желаемая дата"]))
        # без статуса end_status_date не учитывается
        self.assertEqual(dev_deadline([{"key": "J1", "end_status_date": "2026-09-01"}], "J1")["dates"], [])
        self.assertIsNone(dev_deadline(parts, "J999"))

    def test_target_tile(self):
        from report_service.report_builder import dev_deadline
        from report_service.templates import _target_tile
        html = _target_tile({"dev_deadline": dev_deadline([ROADMAP_J028], "J028")}, "2026-11-13")
        self.assertIn("Срок завершения разработки", html)
        self.assertIn("осталось 2 месяца 18 дней", html)  # до конца 01.2027 (Дата МП позже плановой)
        self.assertIn("01.2027", html)
        self.assertIn("Дата МП", html)
        self.assertNotIn("установил", html)
        self.assertNotIn("12.2026", html)
        far = dev_deadline([{"key": "J1", "mp_date": "2027-01-01", "end_status": "desired",
                             "end_status_date": "2027-09-01"}], "J1")
        html = _target_tile({"dev_deadline": far}, "2026-11-13")
        self.assertIn("Желаемая дата", html)
        self.assertIn("09.2027", html)
        self.assertNotIn("Дата МП", html)
        late = dev_deadline([{"key": "J1", "mp_date": "2026-09-01"}], "J1")
        self.assertIn("просрочен на 1 месяц 14 дней", _target_tile({"dev_deadline": late}, "2026-11-13"))
        no_dates = dev_deadline([{"key": "J1"}], "J1")
        self.assertIn("не задан", _target_tile({"dev_deadline": no_dates}, "2026-11-13"))
        self.assertIn("не задан", _target_tile({"dev_deadline": None}, "2026-11-13"))
        self.assertIn("нет данных", _target_tile({}, "2026-11-13"))
        # старый отчёт без сохранённого срока: Дата МП из главного сервиса на момент просмотра
        live = {"ok": True, "value": dev_deadline([ROADMAP_J028], "J028"), "at": "14.11.2026"}
        html = _target_tile({}, "2026-11-13", live)
        self.assertIn("осталось 2 месяца 18 дней", html)
        self.assertNotIn("по данным главного сервиса", html)
        self.assertIn("нет данных", _target_tile({}, "2026-11-13", {"ok": False}))
        # сохранённое значение важнее живого
        saved = {"dev_deadline": dev_deadline([{"key": "J1", "mp_date": "2026-12-01"}], "J1")}
        self.assertIn("12.2026", _target_tile(saved, "2026-11-13", live))
        self.assertIn("разработка завершена", _target_tile({"dev_completed": "24.04.2023"}, "2026-11-13"))
        done = dev_deadline([{"key": "J2", "dev_done": True, "dev_done_date": "13.02.2026"}], "J2")
        self.assertIn("13.02.2026", _target_tile({"dev_deadline": done}, "2026-11-13"))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite3")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_generate_and_chain(self):
        c = FakeClient()
        rid1 = service.generate_report(c, self.conn, "J028", "Горский С.Ю.", date(2026, 10, 1),
                                       now=datetime(2026, 11, 13, 12, 0))
        r1 = db.get_report(self.conn, rid1)
        p = r1["payload"]
        self.assertEqual(r1["created_at"], "2026-11-13T12:00:00")
        self.assertEqual(p["project"]["manager"], "Горский С.Ю.")
        self.assertEqual([d["kind"] for d in p["project"]["dev_deadline"]["dates"]], ["planned", "mp"])
        self.assertEqual([m["name"] for m in p["closed_milestones"]], ["Опытный образец"])
        self.assertEqual([m["name"] for m in p["upcoming_milestones"]], ["Постановка"])
        self.assertEqual([s["version_id"] for s in p["closed_stages"]], ["2"])
        self.assertEqual(p["current_stages"][0]["original_date"], "2026-10-15")
        self.assertTrue(db.verify(r1))
        h = p["current_stages"][0]["hours"]
        self.assertEqual((h["total"], h["period"]), (36.0, 25.0))  # период с 01.10.2026
        self.assertEqual([(r["subdivision"], r["total"], r["period"]) for r in h["by_subdivision"]],
                         [("КО", 30.0, 20.0), ("ОРПО", 5.0, 5.0), ("Подразделение не указано", 1.0, 0.0)])
        self.assertEqual(p["closed_stages"][0]["hours"]["total"], 0.0)
        # трудозатраты по проекту: все этапы + списания вне этапов (версия без id, 99 ч без недель — не входят)
        ph = p["project_hours"]
        self.assertEqual((ph["total"], ph["period"], ph["since"]), (36.0, 25.0, "2026-08-03"))
        self.assertEqual([r["subdivision"] for r in ph["by_subdivision"]], ["КО", "ОРПО", "Подразделение не указано"])
        html = templates.report_page(r1, True)
        self.assertIn("Трудозатраты по проекту", html)
        self.assertIn("Всего по проекту", html)
        self.assertIn("учёт с 03.08.2026", html)
        # разбивка по подразделениям — отдельно для общих часов и для часов за период
        blocks = re.findall(r'<details class="phd">.*?</details>', html, re.S)
        self.assertEqual(len(blocks), 2)
        self.assertIn("(3)", blocks[0])  # всего: КО, ОРПО, не указано
        self.assertIn("(2)", blocks[1])  # за период: «не указано» без часов за период — не показывается
        self.assertNotIn("Подразделение не указано", blocks[1])
        self.assertIn("80%", blocks[1])  # КО: 20 из 25 ч за период
        self.assertEqual(p["hours_summary"]["current_period"], 25.0)
        self.assertEqual(p["subdivision_colors"], {"КО": "#52c41a"})
        html = templates.report_page(r1, True)
        self.assertIn("Трудозатраты по подразделениям", html)
        self.assertIn("ОРПО", html)

        # второй отчёт: этап 1 закрылся, ключевая точка «Постановка» прошла
        c.stages_data[0]["is_closed"] = True
        rid2 = service.generate_report(c, self.conn, "J028", "Горский С.Ю.", now=datetime(2027, 1, 10, 9, 0))
        p2 = db.get_report(self.conn, rid2)["payload"]
        self.assertEqual(p2["period_start"], "2026-11-13")
        self.assertEqual(p2["previous_report_id"], rid1)
        self.assertEqual([s["version_id"] for s in p2["closed_stages"]], ["1"])
        self.assertEqual(p2["closed_stages"][0]["deviation_days"], 46)
        self.assertEqual([m["name"] for m in p2["closed_milestones"]], ["Постановка"])

    def test_archive_filter_by_project(self):
        c = FakeClient()
        service.generate_report(c, self.conn, "J028", "a", date(2026, 10, 1))
        service.generate_report(c, self.conn, "J028", "b", date(2026, 10, 1))
        self.assertEqual(len(db.all_reports(self.conn)), 2)
        self.assertEqual(len(db.all_reports(self.conn, "J028")), 2)
        self.assertEqual(db.all_reports(self.conn, "J090"), [])
        self.assertEqual(db.archived_projects(self.conn), [("J028", "X", 2)])

    def test_locked_report_is_immutable(self):
        rid = service.generate_report(FakeClient(), self.conn, "J028", "x", date(2026, 10, 1))
        payload = db.get_report(self.conn, rid)["payload"]
        # черновик можно пересобрать и удалить
        self.assertTrue(db.update_report_payload(self.conn, rid, payload))
        db.lock_report(self.conn, rid, "Иванов")
        # зафиксированный отчёт — нельзя ни изменить, ни удалить
        with self.assertRaises(sqlite3.IntegrityError):
            db.update_report_payload(self.conn, rid, payload)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute("UPDATE reports SET author='y' WHERE id=?", (rid,))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute("DELETE FROM reports WHERE id=?", (rid,))
        with self.assertRaises(sqlite3.IntegrityError):
            db.delete_draft_report(self.conn, rid)
        self.assertEqual(db.get_report(self.conn, rid)["author"], "x")

    def test_refresh_report_keeps_notes_and_edits(self):
        c = FakeClient()
        rid = service.generate_report(c, self.conn, "J028", "x", date(2026, 10, 1),
                                      now=datetime(2026, 11, 13, 12, 0))
        before = db.get_report(self.conn, rid)
        db.set_note_text(self.conn, rid, "2", "Ждём платы")
        db.add_note_image(self.conn, rid, "2", "image/png", PNG_1PX)
        db.set_stage_removed(self.conn, rid, "1", True)
        db.set_stage_description(self.conn, rid, "2", "Свой текст")
        # главный сервис за это время изменился
        c.status_data[0]["Менеджер проекта"] = "Новый Менеджер"
        c.status_data[0]["Наименование проекта"] = "X (новое название)"
        c.stages_data[2]["planned_date"] = "2025-02-01"

        service.refresh_report(c, self.conn, rid)
        after = db.get_report(self.conn, rid)
        # дата отчёта, период, автор и предыдущий отчёт не меняются
        self.assertEqual(after["created_at"], before["created_at"])
        self.assertEqual(after["period_start"], before["period_start"])
        self.assertEqual(after["author"], before["author"])
        self.assertEqual(after["payload"]["previous_report_id"], before["payload"]["previous_report_id"])
        # данные из главного сервиса обновились
        self.assertEqual(after["payload"]["project"]["manager"], "Новый Менеджер")
        self.assertEqual(after["project_name"], "X (новое название)")
        self.assertNotEqual(after["payload_sha256"], before["payload_sha256"])
        self.assertTrue(db.verify(after))
        # примечания, изображения, удалённые этапы и правки сохранились
        notes = db.get_notes(self.conn, rid, with_data=True)
        self.assertEqual(notes["2"]["text"], "Ждём платы")
        self.assertEqual(notes["2"]["images"][0]["data"], PNG_1PX)
        edits = db.get_edits(self.conn, rid)
        self.assertTrue(edits["1"]["removed"])
        self.assertEqual(edits["2"]["description"], "Свой текст")
        # страница отчёта: удалённый этап остаётся удалённым, примечание на месте
        html = templates.report_page(after, True, notes=db.get_notes(self.conn, rid), edits=edits)
        self.assertIn("Ждём платы", html)
        self.assertIn("Удалены из отчёта", html)
        self.assertIn("Свой текст", html)
        self.assertIn("openRefresh()", html)  # у черновика есть кнопка обновления данных
        # зафиксированный отчёт пересобрать нельзя
        db.lock_report(self.conn, rid, "Иванов")
        with self.assertRaises(service.LockedReport):
            service.refresh_report(c, self.conn, rid)

    def test_delete_draft_report(self):
        rid = service.generate_report(FakeClient(), self.conn, "J028", "x", date(2026, 10, 1))
        db.set_note_text(self.conn, rid, "1", "примечание")
        db.add_note_image(self.conn, rid, "1", "image/png", PNG_1PX)
        db.set_stage_removed(self.conn, rid, "2", True)
        self.assertTrue(db.delete_draft_report(self.conn, rid))
        self.assertIsNone(db.get_report(self.conn, rid))
        # примечания и правки удалённого отчёта тоже удалены
        self.assertEqual(db.get_notes(self.conn, rid, with_data=True), {})
        self.assertEqual(db.get_edits(self.conn, rid), {})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 0)
        # повторно удалить нечего
        self.assertFalse(db.delete_draft_report(self.conn, rid))


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


class NotesTests(unittest.TestCase):
    """Примечания к этапам: правятся свободно, отчёт и его контрольная сумма не меняются."""

    def setUp(self):
        import threading
        from http.server import ThreadingHTTPServer
        from report_service import config, web
        self.tmp = tempfile.TemporaryDirectory()
        self._old_db = config.DB_PATH
        config.DB_PATH = Path(self.tmp.name) / "t.sqlite3"
        self.conn = db.connect()
        self.rid = service.generate_report(FakeClient(), self.conn, "J028", "x", date(2026, 10, 1),
                                           now=datetime(2026, 11, 13, 12, 0))
        self._old_live = web._live_deadline
        web._live_deadline = lambda rep: None  # не ходить в главный сервис
        self._old_client = web.CLIENT
        web.CLIENT = FakeClient()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        from report_service import config, web
        self.srv.shutdown()
        self.srv.server_close()
        web._live_deadline = self._old_live
        web.CLIENT = self._old_client
        config.DB_PATH = self._old_db
        self.conn.close()
        self.tmp.cleanup()

    def req(self, path, data=None, ctype=None):
        import json as _json
        import urllib.error
        import urllib.request
        r = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        if ctype:
            r.add_header("Content-Type", ctype)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(r, timeout=10) as resp:
                body, status, rtype = resp.read(), resp.status, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as ex:
            body, status, rtype = ex.read(), ex.code, ex.headers.get("Content-Type", "")
        return status, (_json.loads(body) if "json" in rtype else body)

    def test_note_text_and_images(self):
        import json as _json
        sha = db.get_report(self.conn, self.rid)["payload_sha256"]
        st, j = self.req(f"/reports/{self.rid}/notes/1", _json.dumps({"text": " Ждём платы <b>"}).encode(),
                         "application/json")
        self.assertEqual((st, j), (200, {"ok": True}))
        st, j = self.req(f"/reports/{self.rid}/notes/1/images", PNG_1PX, "image/png")
        self.assertEqual(st, 200)
        img = j["id"]
        st, body = self.req(f"/notes/images/{img}")
        self.assertEqual((st, body), (200, PNG_1PX))
        # текст правится повторно
        self.req(f"/reports/{self.rid}/notes/1", _json.dumps({"text": "Платы пришли"}).encode(), "application/json")
        notes = db.get_notes(self.conn, self.rid)
        self.assertEqual(notes["1"]["text"], "Платы пришли")
        self.assertEqual([i["id"] for i in notes["1"]["images"]], [img])
        # страница отчёта показывает примечание, отчёт не изменился
        st, html = self.req(f"/reports/{self.rid}")
        html = html.decode("utf-8")
        self.assertIn("Примечание", html)
        self.assertIn("Платы пришли", html)
        self.assertIn(f"/notes/images/{img}", html)
        self.assertIn("✔ целостность подтверждена", html)
        self.assertEqual(db.get_report(self.conn, self.rid)["payload_sha256"], sha)
        # скачанный HTML — с встроенным изображением и без редактора
        st, html = self.req(f"/reports/{self.rid}/download")
        html = html.decode("utf-8")
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn('<dialog id="noteDlg"', html)
        self.assertNotIn("openNote(", html)
        # JSON отчёта содержит примечания
        st, j = self.req(f"/reports/{self.rid}.json")
        self.assertEqual(j["stage_notes"]["1"]["text"], "Платы пришли")
        # удаление изображения
        st, j = self.req(f"/reports/{self.rid}/notes/1/images/{img}/delete", b"")
        self.assertEqual(st, 200)
        self.assertEqual(db.get_notes(self.conn, self.rid)["1"]["images"], [])
        st, _ = self.req(f"/notes/images/{img}")
        self.assertEqual(st, 404)

    def test_notes_validation(self):
        import json as _json
        # не изображение (в т.ч. SVG) — отклоняется
        st, j = self.req(f"/reports/{self.rid}/notes/1/images", b"<svg onload=alert(1)>", "image/svg+xml")
        self.assertEqual(st, 400)
        # этапа нет в отчёте / отчёта нет
        st, _ = self.req(f"/reports/{self.rid}/notes/999", _json.dumps({"text": "x"}).encode(), "application/json")
        self.assertEqual(st, 404)
        st, _ = self.req("/reports/777/notes/1", _json.dumps({"text": "x"}).encode(), "application/json")
        self.assertEqual(st, 404)
        # чужое изображение через другой отчёт/этап не удаляется
        img = db.add_note_image(self.conn, self.rid, "1", "image/png", PNG_1PX)
        st, _ = self.req(f"/reports/{self.rid}/notes/2/images/{img}/delete", b"")
        self.assertEqual(st, 404)
        self.assertEqual(len(db.get_notes(self.conn, self.rid)["1"]["images"]), 1)

    def test_stage_edits_and_lock(self):
        import json as _json
        import sqlite3
        from urllib.parse import urlencode
        rep = db.get_report(self.conn, self.rid)
        sha = rep["payload_sha256"]
        stages = rep["payload"]["current_stages"] + rep["payload"]["closed_stages"]
        self.assertGreaterEqual(len(stages), 2)
        a, b = stages[0], stages[1]
        # правка результатов
        st, j = self.req(f"/reports/{self.rid}/stages/{a['version_id']}/description",
                         _json.dumps({"text": "Получен опытный образец <i>"}).encode(), "application/json")
        self.assertEqual((st, j), (200, {"ok": True}))
        st, html = self.req(f"/reports/{self.rid}")
        html = html.decode("utf-8")
        self.assertIn("Получен опытный образец &lt;i&gt;", html)
        self.assertIn('class="edited"', html)
        self.assertIn("Зафиксировать отчёт", html)
        if rep["payload"]["closed_stages"]:
            self.assertIn("Полученные результаты", html)
        self.assertNotIn("Ожидаемые результаты", html)
        # удаление этапа и возврат
        st, _ = self.req(f"/reports/{self.rid}/stages/{b['version_id']}/remove", b"{}", "application/json")
        self.assertEqual(st, 200)
        html = self.req(f"/reports/{self.rid}")[1].decode("utf-8")
        self.assertIn("Удалены из отчёта", html)
        self.assertNotIn(f'class="sdel" data-vid="{b["version_id"]}"', html)
        self.req(f"/reports/{self.rid}/stages/{b['version_id']}/restore", b"{}", "application/json")
        self.assertFalse(db.get_edits(self.conn, self.rid)[b["version_id"]]["removed"])
        self.req(f"/reports/{self.rid}/stages/{b['version_id']}/remove", b"{}", "application/json")
        # возврат исходного текста
        self.req(f"/reports/{self.rid}/stages/{a['version_id']}/description",
                 _json.dumps({"text": None}).encode(), "application/json")
        self.assertIsNone(db.get_edits(self.conn, self.rid)[a["version_id"]]["description"])
        self.req(f"/reports/{self.rid}/stages/{a['version_id']}/description",
                 _json.dumps({"text": "Итог"}).encode(), "application/json")
        # в архиве — черновик
        self.assertIn("черновик", self.req("/reports")[1].decode("utf-8"))
        # фиксация: уведомление, редакторов больше нет
        st, html = self.req(f"/reports/{self.rid}/lock", urlencode({"locked_by": "Иванов"}).encode(),
                            "application/x-www-form-urlencoded")
        html = html.decode("utf-8")
        self.assertEqual(st, 200)
        self.assertIn('id="lockToast"', html)
        self.assertIn("Версию изменить больше будет нельзя", html)
        self.assertIn("Зафиксирован", html)
        for marker in ("openDesc(this)", "removeStage(this)", "openNote(this)", "openLock()", '<dialog id="noteDlg"'):
            self.assertNotIn(marker, html)
        self.assertIn("Итог", html)  # правки сохранились
        self.assertIn("✔ целостность подтверждена", html)
        self.assertIn("зафиксирован", self.req("/reports")[1].decode("utf-8"))
        # без ?locked=1 уведомления нет
        self.assertNotIn('id="lockToast"', self.req(f"/reports/{self.rid}")[1].decode("utf-8"))
        # любые правки отклоняются
        for path, body in ((f"stages/{a['version_id']}/description", _json.dumps({"text": "x"}).encode()),
                           (f"stages/{a['version_id']}/remove", b"{}"),
                           (f"stages/{b['version_id']}/restore", b"{}"),
                           (f"notes/{a['version_id']}", _json.dumps({"text": "x"}).encode())):
            st, j = self.req(f"/reports/{self.rid}/{path}", body, "application/json")
            self.assertEqual(st, 409, path)
        st, _ = self.req(f"/reports/{self.rid}/notes/{a['version_id']}/images", PNG_1PX, "image/png")
        self.assertEqual(st, 409)
        # и на уровне БД
        with self.assertRaises(sqlite3.IntegrityError):
            db.set_stage_description(self.conn, self.rid, a["version_id"], "x")
        with self.assertRaises(sqlite3.IntegrityError):
            db.set_note_text(self.conn, self.rid, a["version_id"], "x")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute("DELETE FROM report_locks")
        # повторная фиксация ничего не меняет
        first = db.get_lock(self.conn, self.rid)
        self.req(f"/reports/{self.rid}/lock", urlencode({"locked_by": "Петров"}).encode(),
                 "application/x-www-form-urlencoded")
        self.assertEqual(db.get_lock(self.conn, self.rid), first)
        # сам отчёт не менялся; JSON содержит правки
        self.assertEqual(db.get_report(self.conn, self.rid)["payload_sha256"], sha)
        j = self.req(f"/reports/{self.rid}.json")[1]
        self.assertEqual(j["stage_edits"][a["version_id"]]["description"], "Итог")
        self.assertEqual(j["lock"]["locked_by"], "Иванов")

    def test_note_text_is_escaped(self):
        db.set_note_text(self.conn, self.rid, "1", '<script>alert(1)</script>')
        rep = db.get_report(self.conn, self.rid)
        html = templates.report_page(rep, True, notes=db.get_notes(self.conn, self.rid))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_group_notes(self):
        """Примечание можно поставить сводной группе подразделения — как отдельному этапу."""
        import json as _json
        from urllib.parse import quote
        rep = db.get_report(self.conn, self.rid)
        html = self.req(f"/reports/{self.rid}")[1].decode("utf-8")
        self.assertIn("Примечание", html)
        name = templates.NO_SUBDIVISION  # у этапов FakeClient нет тега подразделения
        key = templates.group_note_key("current", name)
        self.assertIn(f'data-vid="{key}"', html)
        st, j = self.req(f"/reports/{self.rid}/notes/{quote(key)}",
                         _json.dumps({"text": "Сводка по подразделению"}).encode(), "application/json")
        self.assertEqual((st, j), (200, {"ok": True}))
        st, j = self.req(f"/reports/{self.rid}/notes/{quote(key)}/images", PNG_1PX, "image/png")
        self.assertEqual(st, 200)
        html = self.req(f"/reports/{self.rid}")[1].decode("utf-8")
        self.assertIn("Сводка по подразделению", html)
        self.assertIn(f"/notes/images/{j['id']}", html)
        # примечание группы попало в редактируемый слой и в JSON отчёта
        notes = db.get_notes(self.conn, self.rid)
        self.assertEqual(notes[key]["text"], "Сводка по подразделению")
        self.assertEqual(self.req(f"/reports/{self.rid}.json")[1]["stage_notes"][key]["text"],
                         "Сводка по подразделению")
        # несуществующая группа и несуществующий раздел — 404
        for bad in ("grp:current:Такого подразделения нет", "grp:latest:" + name, "grp:" + name):
            st, _ = self.req(f"/reports/{self.rid}/notes/{quote(bad)}",
                             _json.dumps({"text": "x"}).encode(), "application/json")
            self.assertEqual(st, 404, bad)
        # после фиксации примечание к группе изменить нельзя
        from urllib.parse import urlencode
        self.req(f"/reports/{self.rid}/lock", urlencode({"locked_by": "Иванов"}).encode(),
                 "application/x-www-form-urlencoded")
        st, _ = self.req(f"/reports/{self.rid}/notes/{quote(key)}",
                         _json.dumps({"text": "x"}).encode(), "application/json")
        self.assertEqual(st, 409)

    def test_refresh_endpoint(self):
        """Кнопка «Обновить данные» пересобирает черновик и сохраняет примечания."""
        import json as _json
        db.set_note_text(self.conn, self.rid, "1", "примечание")
        before = db.get_report(self.conn, self.rid)
        st, html = self.req(f"/reports/{self.rid}/refresh", b"")
        self.assertEqual(st, 200)
        html = html.decode("utf-8")
        self.assertIn("Данные обновлены", html)
        self.assertIn("примечание", html)
        after = db.get_report(self.conn, self.rid)
        self.assertEqual((after["created_at"], after["period_start"]),
                         (before["created_at"], before["period_start"]))
        self.assertTrue(db.verify(after))
        # кнопка и диалог обновления есть только у черновика
        self.assertIn("openRefresh()", html)
        # после фиксации — отказ
        from urllib.parse import urlencode
        self.req(f"/reports/{self.rid}/lock", urlencode({"locked_by": "Иванов"}).encode(),
                 "application/x-www-form-urlencoded")
        st, body = self.req(f"/reports/{self.rid}/refresh", b"")
        self.assertEqual(st, 409)

    def test_delete_endpoint(self):
        from urllib.parse import urlencode
        # в архиве есть кнопка удаления только у черновика
        self.assertIn("askDelete(this)", self.req("/reports")[1].decode("utf-8"))
        # зафиксированный отчёт удалить нельзя
        db.lock_report(self.conn, self.rid, "Иванов")
        st, _ = self.req(f"/reports/{self.rid}/delete", b"")
        self.assertEqual(st, 409)
        self.assertIsNotNone(db.get_report(self.conn, self.rid))
        # черновик удаляется и запись исчезает из архива
        rid2 = service.generate_report(FakeClient(), self.conn, "J028", "y", date(2026, 10, 1),
                                       now=datetime(2026, 11, 20, 12, 0))
        db.set_note_text(self.conn, rid2, "1", "x")
        st, html = self.req(f"/reports/{rid2}/delete", b"")
        self.assertEqual(st, 200)
        self.assertIn(f"Черновик отчёта №{rid2} удалён", html.decode("utf-8"))
        self.assertIsNone(db.get_report(self.conn, rid2))
        self.assertEqual(db.get_notes(self.conn, rid2), {})
        self.assertNotIn(f"№{rid2}</td>", self.req("/reports")[1].decode("utf-8"))
        # удалить несуществующий отчёт — 404
        st, _ = self.req(f"/reports/{rid2}/delete", b"")
        self.assertEqual(st, 404)


class ClientGuardTests(unittest.TestCase):
    def test_write_requests_refused(self):
        c = MainClient("http://127.0.0.1:9/api/v1")
        with self.assertRaises(MainServiceError) as cm:
            c._request("POST", "/weekly-report/generate", auth=False)
        self.assertIn("Запрещённый", str(cm.exception))
        with self.assertRaises(MainServiceError):
            c._request("PUT", "/portfolio/project-groups", auth=False)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db_path = self.dir / "reports.sqlite3"
        self.bdir = self.dir / "backups"
        conn = db.connect(self.db_path)
        self.rid = service.generate_report(FakeClient(), conn, "J028", "x", date(2026, 10, 1))
        db.set_note_text(conn, self.rid, "1", "примечание")
        db.add_note_image(conn, self.rid, "1", "image/png", PNG_1PX)
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_is_full_and_valid(self):
        from report_service import backup
        path = backup.make_backup(self.db_path, self.bdir, keep=5, now=datetime(2026, 11, 16, 10, 0))
        self.assertEqual(path.name, "reports_20261116_100000.sqlite3")
        self.assertFalse(list(self.bdir.glob("*.tmp")))
        copy = db.connect(path)
        rep = db.get_report(copy, self.rid)
        self.assertTrue(db.verify(rep))  # отчёт и контрольная сумма скопированы как есть
        notes = db.get_notes(copy, self.rid, with_data=True)
        self.assertEqual(notes["1"]["text"], "примечание")
        self.assertEqual(notes["1"]["images"][0]["data"], PNG_1PX)
        copy.close()

    def test_rotation_and_schedule(self):
        from report_service import backup
        for h in range(5):
            backup.make_backup(self.db_path, self.bdir, keep=3, now=datetime(2026, 11, 16, h, 0))
        (self.bdir / "before_restore_20261101_000000.sqlite3").write_bytes(b"x")  # не трогается ротацией
        backup.make_backup(self.db_path, self.bdir, keep=3, now=datetime(2026, 11, 16, 5, 0))
        names = [b["name"] for b in backup.list_backups(self.bdir)]
        self.assertEqual(names, ["reports_20261116_050000.sqlite3", "reports_20261116_040000.sqlite3",
                                 "reports_20261116_030000.sqlite3"])
        self.assertTrue((self.bdir / "before_restore_20261101_000000.sqlite3").exists())
        last = backup.last_backup(self.bdir)
        self.assertFalse(backup.is_due(last, datetime(2026, 11, 17, 4, 59), 24))
        self.assertTrue(backup.is_due(last, datetime(2026, 11, 17, 5, 0), 24))
        self.assertTrue(backup.is_due(None, datetime(2026, 11, 17), 24))
        self.assertFalse(backup.is_due(None, datetime(2026, 11, 17), 0))  # 0 — выключено

    def test_same_second_does_not_overwrite(self):
        from report_service import backup
        t = datetime(2026, 11, 16, 10, 0)
        a = backup.make_backup(self.db_path, self.bdir, keep=10, now=t)
        b = backup.make_backup(self.db_path, self.bdir, keep=10, now=t)
        self.assertNotEqual(a, b)
        self.assertEqual(len(backup.list_backups(self.bdir)), 2)

    def test_missing_db(self):
        from report_service import backup
        with self.assertRaises(backup.BackupError):
            backup.make_backup(self.dir / "nope.sqlite3", self.bdir)


if __name__ == "__main__":
    unittest.main()
