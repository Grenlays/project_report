"""Формирование отчёта по проекту.

Термины главного сервиса:
  * ключевые точки  — /portfolio/project-milestones (название, месяц, год, комментарий);
  * этапы           — версии Redmine из /portfolio/calendar-events
                      (плановая дата, ожидаемые результаты, признак закрытия);
  * переносы этапов — /portfolio/version-metadata/{id}/date-changes.

У ключевой точки в главном сервисе хранится одна дата. Поэтому «плановая»
дата закрытой точки — дата, с которой точка впервые попала в наш отчёт
(базовый план), а «фактическая» — её текущая дата в главном сервисе.
Если точка в отчётах ещё не встречалась, план = факт.
"""
import re
from datetime import date, datetime

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
          "сентябрь", "октябрь", "ноябрь", "декабрь"]

_CODE_RE = re.compile(r"^\s*([A-Za-zА-Яа-я]+)_?(\d+)")


def project_code(value: str):
    """'J_028' / 'J028_Портативный стимулятор' -> 'J028'."""
    if not value:
        return None
    m = _CODE_RE.match(value)
    if not m:
        return None
    return (m.group(1) + m.group(2)).upper()


def _parse_date(s):
    if not s:
        return None
    s = str(s)[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _ym(y, m):
    return int(y) * 12 + int(m) - 1


def month_label(y, m):
    return f"{MONTHS[int(m) - 1]} {y}"


# --- ключевые точки --------------------------------------------------------
def _milestone_keys(items):
    """Стабильный ключ точки: название|комментарий (+№ при дублях)."""
    seen = {}
    out = []
    for it in sorted(items, key=lambda x: (x["name"], x.get("comment") or "", x["year"], x["month"])):
        base = f'{it["name"]}|{(it.get("comment") or "").strip()}'
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base}#{seen[base]}"
        out.append((key, it))
    return out


def _snapshot_milestones(items):
    return {k: {"name": it["name"], "comment": it.get("comment") or "",
                "year": int(it["year"]), "month": int(it["month"])}
            for k, it in _milestone_keys(items)}


def build_milestones(current_items, prev_reports, now: date, period_start: date):
    cur = _snapshot_milestones(current_items)
    now_ym = _ym(now.year, now.month)

    # базовый план: дата при первом появлении точки в наших отчётах
    baseline = {}
    for rep in prev_reports:
        for k, v in rep["snapshot"]["milestones"].items():
            baseline.setdefault(k, v)
    prev = prev_reports[-1] if prev_reports else None
    prev_ms = prev["snapshot"]["milestones"] if prev else {}
    prev_now_ym = None
    if prev:
        pd = _parse_date(prev["created_at"])
        prev_now_ym = _ym(pd.year, pd.month)
    start_ym = _ym(period_start.year, period_start.month)

    upcoming, closed = [], []
    for k, v in cur.items():
        ym = _ym(v["year"], v["month"])
        if ym >= now_ym:
            upcoming.append({"key": k, **v, "label": month_label(v["year"], v["month"])})
            continue
        # точка в прошлом — попадает в отчёт, если закрылась в отчётном периоде
        if k in prev_ms:
            was_open = _ym(prev_ms[k]["year"], prev_ms[k]["month"]) >= prev_now_ym
        else:
            was_open = ym >= start_ym
        if not was_open:
            continue
        base = baseline.get(k, v)
        dev = ym - _ym(base["year"], base["month"])
        closed.append({
            "key": k, "name": v["name"], "comment": v["comment"],
            "plan_year": base["year"], "plan_month": base["month"],
            "plan_label": month_label(base["year"], base["month"]),
            "fact_year": v["year"], "fact_month": v["month"],
            "fact_label": month_label(v["year"], v["month"]),
            "deviation_months": dev,
        })
    upcoming.sort(key=lambda x: (_ym(x["year"], x["month"]), x["name"]))
    closed.sort(key=lambda x: (_ym(x["fact_year"], x["fact_month"]), x["name"]))
    return upcoming, closed, cur


# --- этапы ----------------------------------------------------------------
def _snapshot_stage(s):
    return {
        "version_id": str(s["version_id"]),
        "name": s.get("version_name") or "",
        "planned_date": s.get("planned_date"),
        "is_closed": bool(s.get("is_closed")),
        "description": s.get("description") or "",
        "subdivision": s.get("subdivision_tag") or "",
        "last_hours_date": s.get("last_hours_date"),
        "approval_status": s.get("approval_status") or "",
    }


def select_stages(current_items, prev_reports, period_start: date):
    """Делит этапы проекта на текущие и закрытые с момента предыдущего отчёта."""
    cur = {str(s["version_id"]): _snapshot_stage(s) for s in current_items if not s.get("not_in_project")}
    prev = prev_reports[-1] if prev_reports else None
    prev_st = prev["snapshot"]["stages"] if prev else {}

    current, closed = [], []
    for vid, s in cur.items():
        if not s["is_closed"]:
            current.append(s)
            continue
        if vid in prev_st:
            if prev_st[vid]["is_closed"]:
                continue  # уже был закрыт в прошлом отчёте
            closed.append(s)
        else:
            dates = [d for d in (_parse_date(s["planned_date"]), _parse_date(s["last_hours_date"])) if d]
            if dates and max(dates) >= period_start:
                closed.append(s)
    return current, closed, cur


def original_date(stage, changes, prev_reports):
    """Первоначальная плановая дата этапа."""
    ch = sorted((c for c in (changes or []) if c.get("old_date")), key=lambda c: c.get("changed_at") or "")
    if ch:
        return ch[0]["old_date"][:10], len(ch)
    for rep in prev_reports:
        st = rep["snapshot"]["stages"].get(stage["version_id"])
        if st and st.get("planned_date"):
            return st["planned_date"][:10], 0
    return (stage["planned_date"] or "")[:10] or None, 0


def _days(a, b):
    a, b = _parse_date(a), _parse_date(b)
    return (b - a).days if a and b else None


def enrich_stages(current, closed, changes_by_id, prev_reports):
    cur_out, closed_out = [], []
    for s in current:
        orig, n = original_date(s, changes_by_id.get(s["version_id"]), prev_reports)
        cur_out.append({**s, "original_date": orig, "transfers": n,
                        "deviation_days": _days(orig, s["planned_date"])})
    for s in closed:
        orig, n = original_date(s, changes_by_id.get(s["version_id"]), prev_reports)
        closed_out.append({**s, "original_date": orig, "fact_date": (s["planned_date"] or "")[:10] or None,
                           "transfers": n, "deviation_days": _days(orig, s["planned_date"])})
    key = lambda x: (x["planned_date"] or "9999", x["name"])
    cur_out.sort(key=key)
    closed_out.sort(key=key)
    return cur_out, closed_out


# --- трудозатраты ------------------------------------------------------------
UNKNOWN_SUBDIVISION = "Подразделение не указано"


def stage_hours(project_details, subdivision_map, period_start: date):
    """Трудозатраты по этапам: всего и за отчётный период, с разбивкой по подразделениям.

    За период берутся недели, начинающиеся в день начала периода или позже
    (главный сервис отдаёт трудозатраты с точностью до недели).
    """
    acc = {}
    start = period_start.isoformat()
    for det in project_details:
        for v in det.get("versions") or []:
            vid = v.get("version_id")
            if vid is None:
                continue
            st = acc.setdefault(str(vid), {})
            for u in v.get("users") or []:
                sub = subdivision_map.get(u.get("name")) or UNKNOWN_SUBDIVISION
                rec = st.setdefault(sub, [0.0, 0.0])
                rec[0] += float(u.get("total_hours") or 0)
                rec[1] += sum(float(w.get("hours") or 0) for monday, w in (u.get("weekly_hours") or {}).items()
                              if monday >= start)
    out = {}
    for vid, subs in acc.items():
        rows = sorted(({"subdivision": k, "total": round(t, 2), "period": round(p, 2)} for k, (t, p) in subs.items()),
                      key=lambda r: -r["total"])
        out[vid] = {"total": round(sum(r["total"] for r in rows), 2),
                    "period": round(sum(r["period"] for r in rows), 2),
                    "by_subdivision": rows}
    return out


def project_hours(project_details, subdivision_map, period_start: date, cutoff: date):
    """Трудозатраты по проекту целиком (все этапы и списания вне этапов).

    Считаются по неделям: «всего» — недели, начавшиеся не позже даты отчёта (cutoff),
    «за период» — из них недели, начавшиеся в день начала периода или позже.
    """
    start, end = period_start.isoformat(), cutoff.isoformat()
    subs, first = {}, None
    for det in project_details:
        for v in det.get("versions") or []:
            for u in v.get("users") or []:
                sub = subdivision_map.get(u.get("name")) or UNKNOWN_SUBDIVISION
                for monday, w in (u.get("weekly_hours") or {}).items():
                    if monday > end:
                        continue
                    h = float(w.get("hours") or 0)
                    rec = subs.setdefault(sub, [0.0, 0.0])
                    rec[0] += h
                    if monday >= start:
                        rec[1] += h
                    first = monday if first is None or monday < first else first
    rows = sorted(({"subdivision": k, "total": round(t, 2), "period": round(p, 2)} for k, (t, p) in subs.items()),
                  key=lambda r: (-r["total"], r["subdivision"]))
    return {"total": round(sum(r["total"] for r in rows), 2), "period": round(sum(r["period"] for r in rows), 2),
            "since": first, "by_subdivision": rows}


EMPTY_HOURS = {"total": 0.0, "period": 0.0, "by_subdivision": []}


def attach_hours(stages, hours):
    for s in stages:
        s["hours"] = hours.get(s["version_id"], EMPTY_HOURS)
    return stages


def hours_summary(current, closed):
    tot = lambda xs, k: round(sum(s["hours"][k] for s in xs), 2)
    return {"current_total": tot(current, "total"), "current_period": tot(current, "period"),
            "closed_total": tot(closed, "total"), "closed_period": tot(closed, "period")}


# --- проект ----------------------------------------------------------------
def project_info(status_row, manager_fallback=None):
    g = lambda k: (status_row.get(k) or "").strip() if status_row else ""
    return {
        "id": g("ID проекта"),
        "code": project_code(g("ID проекта")),
        "name": g("Наименование проекта"),
        "direction": g("Направление проекта"),
        "niokr_direction": g("Направление НИОКР"),
        "manager": g("Менеджер проекта") or (manager_fallback or ""),
        "status": g("Статус проекта"),
        "type": g("Тип проекта"),
        "opened": g("Дата открытия"),
        "work_started": g("Дата начала работ"),
        "dev_completed": g("Дата завершения технической разработки проекта"),
    }


DEADLINE_KINDS = {"planned": "Планируемая дата", "mp": "Дата МП", "desired": "Желаемая дата"}


def dev_deadline(roadmap_projects, code):
    """Даты завершения разработки проекта из дорожной карты главного сервиса.

    Берутся «Планируемая дата» (end_status = fixed), «Желаемая дата» (end_status = desired) — обе
    из end_status_date — и «Дата МП» (mp_date). Проект может быть разбит на части (J090, J090#2):
    для каждого вида даты берётся самая поздняя среди частей. Какую дату показывать как срок,
    решает deadline_pick (самую дальнюю).
    """
    parts = [p for p in roadmap_projects or [] if project_code(str(p.get("key", "")).split("#")[0]) == code]
    if not parts:
        return None
    found = {}
    for p in parts:
        cands = []
        if p.get("mp_date"):
            cands.append(("mp", p["mp_date"], p.get("mp_date_by")))
        st = {"fixed": "planned", "desired": "desired"}.get(p.get("end_status"))
        if st and p.get("end_status_date"):
            cands.append((st, p["end_status_date"], p.get("end_status_by")))
        for kind, value, by in cands:
            month = str(value)[:7]
            if kind not in found or month > found[kind]["month"]:
                found[kind] = {"kind": kind, "label": DEADLINE_KINDS[kind], "month": month, "by": by or "", "at": ""}
    dates = [found[k] for k in DEADLINE_KINDS if k in found]
    done = [p.get("dev_done_date") for p in parts if p.get("dev_done")]
    return {"dates": dates,
            "dev_done": bool(parts) and all(p.get("dev_done") for p in parts),
            "dev_done_date": max(done, key=lambda s: _parse_date(s) or date.min) if done else None}


def deadline_pick(dates):
    """Самая дальняя из дат: (месяц 'ГГГГ-ММ', [названия дат с этим месяцем]) или None."""
    known = [d for d in dates or [] if d.get("kind") in DEADLINE_KINDS and d.get("month")]
    if not known:
        return None
    month = max(d["month"] for d in known)
    return month, [DEADLINE_KINDS[d["kind"]] for d in known if d["month"] == month]
