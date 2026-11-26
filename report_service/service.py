"""Сценарии: список проектов и формирование отчёта."""
from datetime import date, datetime, timedelta

from . import config, db
from .report_builder import (attach_hours, build_milestones, dev_deadline, enrich_stages,
                             hours_summary, project_code, project_hours, project_info, select_stages,
                             stage_hours)


class NotFound(Exception):
    pass


class LockedReport(Exception):
    """Отчёт зафиксирован — пересобрать или удалить его нельзя."""


def list_projects(client, conn, show_all=False):
    statuses = client.project_statuses()
    reports = db.last_report_dates(conn)
    out = []
    for row in statuses:
        info = project_info(row)
        if not info["code"]:
            continue
        if not show_all and info["status"] in config.INACTIVE_STATUSES:
            continue
        last, cnt = reports.get(info["code"], (None, 0))
        out.append({**info, "last_report": last, "reports_count": cnt})
    out.sort(key=lambda x: x["code"])
    return out


def find_project(client, code):
    for row in client.project_statuses():
        if project_code(row.get("ID проекта")) == code:
            return row
    raise NotFound(code)


def default_period_start(conn, code):
    prev = db.last_report(conn, code)
    if prev:
        return datetime.fromisoformat(prev["created_at"]).date(), prev
    return date.today() - timedelta(days=config.FIRST_REPORT_DEFAULT_DAYS), None


def _project_details(client, filters, code, extra_names=()):
    names = sorted({n for n in (filters.get("projects") or []) if project_code(n) == code} | set(extra_names))
    return [client.project_detail(n) for n in names]


def live_project_hours(client, rep):
    """Трудозатраты по проекту для отчёта, сформированного до появления этого раздела.
    Считаются по данным главного сервиса за недели до даты отчёта; сам отчёт не меняется."""
    filters = client.filters()
    details = _project_details(client, filters, rep["project_code"])
    hours = project_hours(details, filters.get("subdivision_map") or {},
                          date.fromisoformat(rep["period_start"][:10]), date.fromisoformat(rep["created_at"][:10]))
    colors = filters.get("subdivision_color_map") or {}
    return hours, {r["subdivision"]: colors[r["subdivision"]] for r in hours["by_subdivision"]
                   if r["subdivision"] in colors}


def build_payload(client, code, author, now, period_start, prev, prev_payloads):
    """Собирает содержимое отчёта по данным главного сервиса.

    now — дата и время проведения отчёта; period_start — начало отчётного периода;
    prev — предыдущий отчёт проекта (или None), prev_payloads — его содержимые по возрастанию даты
    (для базовых планов и первоначальных дат этапов).
    """
    status_row = find_project(client, code)

    all_ms = client.milestones()
    all_st = client.stages()
    ms = [m for m in all_ms if project_code(m.get("project")) == code]
    st = [s for s in all_st if project_code(s.get("project_name")) == code]

    filters = client.filters()
    managers = sorted({s.get("manager") for s in st if s.get("manager")})
    info = project_info(status_row, managers[0] if managers else None)
    info["dev_deadline"] = dev_deadline((client.roadmap() or {}).get("projects"), code)
    details = _project_details(client, filters, code, {s["project_name"] for s in st})
    sub_map = filters.get("subdivision_map") or {}
    hours = stage_hours(details, sub_map, period_start)
    proj_hours = project_hours(details, sub_map, period_start, now.date())
    colors = filters.get("subdivision_color_map") or {}

    upcoming, closed_ms, ms_snapshot = build_milestones(ms, prev_payloads, now.date(), period_start)
    current, closed_st, st_snapshot = select_stages(st, prev_payloads, period_start)
    changes = {s["version_id"]: client.stage_date_changes(s["version_id"]) for s in current + closed_st}
    current_out, closed_out = enrich_stages(current, closed_st, changes, prev_payloads)
    attach_hours(current_out, hours)
    attach_hours(closed_out, hours)
    used = {r["subdivision"] for s in current_out + closed_out for r in s["hours"]["by_subdivision"]}
    used |= {r["subdivision"] for r in proj_hours["by_subdivision"]}

    return {
        "format": 2,
        "hours_summary": hours_summary(current_out, closed_out),
        "project_hours": proj_hours,
        "subdivision_colors": {k: v for k, v in colors.items() if k in used},
        "created_at": now.isoformat(),
        "period_start": period_start.isoformat(),
        "previous_report_id": prev["id"] if prev else None,
        "author": author,
        "source": config.MAIN_URL,
        "project": info,
        "upcoming_milestones": upcoming,
        "closed_milestones": closed_ms,
        "current_stages": current_out,
        "closed_stages": closed_out,
        # снимок исходных данных — база для сравнения в следующем отчёте
        "snapshot": {"milestones": ms_snapshot, "stages": st_snapshot, "project_status": status_row},
    }


def generate_report(client, conn, code, author, first_period_start=None, now=None):
    now = now or datetime.now().replace(microsecond=0)
    prev = db.last_report(conn, code)
    if prev:
        period_start = datetime.fromisoformat(prev["created_at"]).date()
    else:
        period_start = first_period_start or (now.date() - timedelta(days=config.FIRST_REPORT_DEFAULT_DAYS))

    prev_payloads = [r["payload"] for r in db.project_reports(conn, code, with_payload=True)]
    payload = build_payload(client, code, author, now, period_start, prev, prev_payloads)
    return db.insert_report(
        conn, project_code=code, project_name=payload["project"]["name"], created_at=payload["created_at"],
        period_start=payload["period_start"], previous_id=payload["previous_report_id"],
        author=author, payload=payload)


def refresh_report(client, conn, report_id, now=None):
    """Пересобирает данные черновика по актуальному состоянию главного сервиса.

    Дата отчёта, отчётный период, автор и предыдущий отчёт не меняются — обновляется только то,
    что берётся из главного сервиса (сроки, статусы, этапы, трудозатраты, ключевые точки).
    Примечания и правки этапов живут в отдельных таблицах по номеру отчёта, поэтому сохраняются:
    заполненные примечания остаются, удалённые этапы остаются удалёнными.
    """
    rep = db.get_report(conn, report_id)
    if not rep:
        raise NotFound(report_id)
    if db.get_lock(conn, report_id):
        raise LockedReport()
    now = now or datetime.fromisoformat(rep["created_at"])
    period_start = date.fromisoformat(rep["period_start"][:10])
    prev = db.get_report(conn, rep["previous_id"]) if rep["previous_id"] else None
    prev_payloads = [r["payload"] for r in db.project_reports(conn, rep["project_code"], with_payload=True)
                     if r["id"] < rep["id"]]
    payload = build_payload(client, rep["project_code"], rep["author"], now, period_start, prev, prev_payloads)
    db.update_report_payload(conn, report_id, payload)
    return payload
