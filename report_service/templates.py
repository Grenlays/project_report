"""HTML-страницы сервиса (серверный рендеринг, без внешних зависимостей)."""
import base64
import calendar
import json
from datetime import date, datetime
from html import escape

from .report_builder import deadline_pick

CSS = """
:root{--bg:#f2f5fb;--card:#fff;--ink:#172033;--muted:#5d6b82;--line:#e3e8f1;--accent:#2457d6;--accent-soft:#e8efff;
--ok:#0f9d58;--ok-soft:#e3f6ec;--warn:#e8890c;--warn-soft:#fff3df;--bad:#e03131;--bad-soft:#ffe9e9;--violet:#7048e8;--violet-soft:#efeaff}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 "Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink)}
header.top{background:linear-gradient(90deg,#14275a,#2457d6);color:#fff;padding:12px 24px;display:flex;gap:24px;align-items:center}
header.top a{color:#d5e2ff;text-decoration:none}header.top a:hover{color:#fff}header.top b{font-size:16px;color:#fff}
main{max-width:1240px;margin:0 auto;padding:22px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:22px 0 10px;display:flex;align-items:center;gap:10px}
h2 .cnt{background:var(--accent);color:#fff;border-radius:10px;padding:0 9px;font-size:12px;line-height:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:14px;box-shadow:0 1px 2px rgba(20,39,90,.05)}
table{width:100%;border-collapse:collapse;background:var(--card)}
th,td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{background:#eef2fa;font-weight:600;font-size:12px;color:#3b4a63;text-transform:uppercase;letter-spacing:.02em}
td.num,th.num{text-align:right;white-space:nowrap}td.date{white-space:nowrap}
.muted{color:var(--muted)}.small{font-size:12px}
.pre{white-space:pre-wrap}
.grid{display:grid;grid-template-columns:220px 1fr;gap:4px 16px}
.grid div:nth-child(odd){color:var(--muted)}
.badge{display:inline-block;padding:1px 9px;border-radius:10px;background:#eef2fa;font-size:12px;white-space:nowrap}
.btn{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 16px;
font-size:14px;cursor:pointer;text-decoration:none}.btn.sec{background:var(--accent-soft);color:var(--accent)}
form.inline{display:flex;gap:12px;align-items:end;flex-wrap:wrap}
label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)}
input,select{font:inherit;padding:6px 8px;border:1px solid #c9d1df;border-radius:6px;min-width:220px}
.empty{color:var(--muted);font-style:italic;padding:10px 4px}
.err{background:var(--bad-soft);border-color:#ffc9c9;color:var(--bad)}
.lock{font-size:12px;color:var(--muted)}
a{color:var(--accent)}
.wrap{overflow-x:auto}

/* --- отчёт --- */
.hero{background:linear-gradient(120deg,#14275a 0%,#2457d6 60%,#4c7dff 100%);color:#fff;border-radius:14px;padding:18px 22px;
display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:start;margin-bottom:14px}
.hero h1{font-size:24px;margin:2px 0 8px}.hero .code{background:rgba(255,255,255,.18);border-radius:6px;padding:1px 8px;font-size:13px;font-weight:600}
.hero .meta{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:13px;color:#dbe6ff}.hero .meta b{color:#fff;font-weight:600}
.hero .right{text-align:right;min-width:210px;max-width:440px;justify-self:end}.hero .date{font-size:20px;font-weight:700}.hero .sub{font-size:12px;color:#cddbff}
.status{display:inline-block;border-radius:14px;padding:3px 12px;font-weight:600;font-size:13px;background:#fff;color:var(--accent);margin-bottom:8px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:6px}
.kpi{background:var(--card);border-radius:12px;padding:10px 16px 12px;border:1px solid var(--line);border-top:4px solid var(--c,#2457d6)}
.kpi .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-weight:600}
.kpi .v{font-size:23px;font-weight:700;color:var(--c,#2457d6);line-height:1.25;margin:4px 0 3px}
.kpi .h{font-size:12px;color:var(--muted)}
.pill.dl-mp{background:var(--accent-soft);color:var(--accent)}.pill.dl-pl{background:var(--ok-soft);color:var(--ok)}
.pill.dl-ds{background:var(--warn-soft);color:#b86a00}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.cols .card{margin:0;padding:0;overflow:hidden}.cols .card h3{margin:0;padding:9px 14px;font-size:13px;color:#fff;background:var(--c)}
.mlist{list-style:none;margin:0;padding:0}.mlist li{display:flex;gap:10px;align-items:baseline;padding:6px 14px;border-bottom:1px solid var(--line)}
.mlist li:last-child{border:0}
.when{flex:0 0 78px;font-weight:600;font-size:12px;color:var(--accent);background:var(--accent-soft);border-radius:6px;text-align:center;padding:1px 0}
.when.now{background:var(--warn-soft);color:var(--warn)}
.mlist .nm{flex:1}.mlist .pf{white-space:nowrap;font-size:12px;color:var(--muted)}
.pill{display:inline-block;border-radius:10px;padding:0 8px;font-size:12px;font-weight:600;white-space:nowrap}
.pill.ok{background:var(--ok-soft);color:var(--ok)}.pill.bad{background:var(--bad-soft);color:var(--bad)}
.pill.warn{background:var(--warn-soft);color:var(--warn)}.pill.early{background:var(--violet-soft);color:var(--violet)}
.stages td{padding:6px 10px}.stages tr.main{cursor:pointer}.stages tr.main:hover td{background:#f7f9ff}
.stages .nm{font-weight:600}.tag{display:inline-block;font-size:11px;color:var(--muted);background:#f0f2f7;border-radius:4px;padding:0 5px;margin-top:2px}
.clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;color:#33415a}
.res{white-space:pre-line;display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden;
font-size:14px;line-height:1.5;color:var(--ink);border-left:3px solid var(--accent-soft);padding-left:9px}
.res.cut{cursor:help;border-left-color:#9db4f0}.res.cut:hover{background:#f4f7ff}
.res.none{color:var(--muted);border-left-color:var(--line)}
.restxt{white-space:pre-line;font-size:14px;line-height:1.55;color:var(--ink)}
#resTip{position:fixed;z-index:60;display:none;max-width:min(560px,92vw);max-height:60vh;overflow:auto;background:#fff;
border:1px solid #c9d6f2;border-radius:10px;box-shadow:0 12px 36px rgba(20,39,90,.25);padding:12px 14px;
white-space:pre-line;font-size:14px;line-height:1.55;color:var(--ink)}
#resTip .t{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);font-weight:600;margin-bottom:6px}
.was{font-size:11px;color:var(--muted)}.was s{color:#8a96aa}
.hrs b{font-size:14px}.hrs .p{font-size:11px;color:var(--ok);font-weight:600}
.tog{color:var(--accent);font-size:16px;width:22px;text-align:center;transition:transform .15s}
tr.main.open .tog{transform:rotate(90deg)}
.phgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px 28px;align-items:start}
.ph{border-left:4px solid var(--c);padding:2px 0 2px 14px}
.ph .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-weight:600}
.ph .v{font-size:26px;font-weight:700;color:var(--c);line-height:1.25;margin:2px 0}.ph .h{font-size:12px;color:var(--muted)}
details.phd{margin-top:12px;border-top:1px solid var(--line);padding-top:8px}
details.phd summary{cursor:pointer;color:var(--accent);font-weight:600;font-size:13px;padding:4px 0}
details.phd .subs{margin-top:6px}
td.notecell{cursor:default;font-size:13px}
.ntext{white-space:pre-wrap;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;color:#33415a}
.nimgs{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.nimgs a{display:block}
.nimgs img{display:block;width:100%;height:auto;border-radius:6px;border:1px solid var(--line);background:#fff}
.nedit{margin-top:4px;background:none;border:1px dashed #b9c4d8;color:var(--accent);border-radius:6px;padding:1px 8px;
font-size:12px;cursor:pointer}.nedit:hover{background:var(--accent-soft)}
dialog.dlg{border:0;border-radius:12px;padding:18px 20px;width:min(640px,94vw);box-shadow:0 12px 40px rgba(20,39,90,.3)}
dialog.dlg::backdrop{background:rgba(20,39,90,.35)}
.dlg h3{margin:0 0 10px;font-size:16px}
.dlg textarea{width:100%;font:inherit;padding:8px;border:1px solid #c9d1df;border-radius:8px;resize:vertical}
.dlg .orig{margin-top:8px;font-size:12px}.dlg .orig summary{cursor:pointer;color:var(--accent)}
.dlg .orig div{white-space:pre-wrap;color:var(--muted);max-height:160px;overflow:auto;margin-top:4px}
.dlg .warn{background:var(--warn-soft);color:#8a4b00;border-radius:8px;padding:10px 12px;margin:0 0 12px;font-size:13px}
.dlg input{width:100%}
.btn.danger{background:var(--bad)}.btn.lockbtn{background:#0f9d58;margin-left:auto}
.edited{display:inline-block;font-size:11px;color:var(--violet);background:var(--violet-soft);border-radius:4px;padding:0 5px;margin-top:3px}
.sdel{display:inline-block;margin-top:3px;background:none;border:0;padding:0;color:#9aa5b8;font-size:11px;cursor:pointer}
.sdel:hover{color:var(--bad);text-decoration:underline}
.removed{font-size:12px;color:var(--muted);margin:-6px 2px 10px}
.removed button{background:none;border:0;color:var(--accent);cursor:pointer;font-size:12px;padding:0;text-decoration:underline}
.lockst{display:inline-block;margin-top:6px;border-radius:8px;padding:2px 10px;font-size:12px;font-weight:600;background:rgba(255,255,255,.95);color:#0f9d58}
.lockst.draft{background:rgba(255,255,255,.18);color:#fff;font-weight:400}
.toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:50;background:#0f5132;color:#fff;border-radius:12px;
padding:14px 18px 14px 20px;box-shadow:0 12px 40px rgba(20,39,90,.35);display:flex;gap:14px;align-items:flex-start;max-width:min(560px,94vw)}
.toast b{display:block;font-size:15px;margin-bottom:2px}.toast button{background:none;border:0;color:#fff;font-size:18px;cursor:pointer;line-height:1}
.dimgs{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.dimg{position:relative}.dimg img{height:90px;max-width:160px;object-fit:cover;border-radius:6px;border:1px solid var(--line)}
.dimg button{position:absolute;top:-6px;right:-6px;width:22px;height:22px;border-radius:50%;border:0;background:var(--bad);
color:#fff;cursor:pointer;font-size:12px;line-height:22px;padding:0}
.upl{display:inline-flex;flex-direction:row;color:var(--accent);cursor:pointer;font-size:13px}
.nerr{color:var(--bad);font-size:13px;min-height:18px;margin-top:6px}
.dbtns{display:flex;justify-content:flex-end;gap:8px;margin-top:8px}
.sarr{display:inline-block;color:var(--sc);font-size:14px;width:16px;transition:transform .15s}
h2.sth.closed .sarr{transform:rotate(-90deg)}h2.sth.closed+.secbody{display:none}
h2.sth.closed{margin-bottom:6px}
.stcard{--sc:#2457d6;--sh:#e4ecff;--sg:#f1f5ff;padding:0;overflow:hidden;border:1px solid #c3cfe6;border-top:5px solid var(--sc);
box-shadow:0 4px 14px rgba(20,39,90,.10)}
.stcard.cl{--sc:#0f9d58;--sh:#dcf2e6;--sg:#eff9f3}
.stcard th{background:var(--sh);color:#22314d;border-bottom:2px solid #c3cfe6}
.stcard .stages td{border-bottom-color:#dfe5f0}
.stages tr.grp td{background:var(--sg,#eef2fa);padding:6px 10px;border-top:1px solid #cfd8ea;border-bottom:1px solid #cfd8ea;
font-size:12px;box-shadow:inset 4px 0 0 var(--sc,#2457d6)}
h2.sth{cursor:pointer;user-select:none;background:#fff;border:1px solid #c3cfe6;border-left:5px solid var(--sc);border-radius:10px;padding:8px 14px;
margin:26px 0 10px;box-shadow:0 1px 3px rgba(20,39,90,.06)}
.stages tr.grp{cursor:pointer;user-select:none}.stages tr.grp:hover td{background:#e3e9f7}
.garr{display:inline-block;width:16px;color:var(--accent);transition:transform .15s}
tbody.g.closed tr:not(.grp){display:none}tbody.g.closed .garr{transform:rotate(-90deg)}
.gname{font-weight:700;color:#14275a;font-size:13px}.gcnt{color:var(--muted);margin-left:6px}
.stages tr.grp td.notecell{font-size:12px}.stages tr.grp td.notecell .ntext{-webkit-line-clamp:3}
.ghrs{float:right;color:#3b4a63;font-weight:600}
tr.link{cursor:pointer}tr.link:hover td{background:#eef3ff}
tr.det{display:none}tr.det.open{display:table-row}tr.det>td{background:#f8faff;padding:12px 16px 14px}
.det-grid{display:grid;grid-template-columns:1.1fr 1fr;gap:22px}
.det-grid h4{margin:0 0 6px;font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.03em}
.subs{width:100%;border-collapse:collapse;background:transparent}.subs td{border:0;padding:3px 4px;font-size:13px}
.subs .bar{height:8px;border-radius:4px;background:var(--c);min-width:2px}
.subs .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--c);margin-right:6px}
.subs tr.tot td{border-top:1px solid var(--line);font-weight:600}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.note{font-size:12px;color:var(--muted);margin:6px 2px 0}
@media (max-width:900px){.kpis,.cols,.det-grid,.phgrid,.hero{grid-template-columns:1fr}.hero .right{justify-self:stretch;max-width:none}}
@media print{header.top,.noprint{display:none!important}body{background:#fff;font-size:12px}main{padding:0;max-width:none}
.hero,.kpi,th,.stages tr.grp td,.stcard,h2.sth,.when,.pill,.subs .bar,.subs .dot,.cols .card h3{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.res{display:block;-webkit-line-clamp:unset;overflow:visible}
.card{box-shadow:none}h2{break-after:avoid}tr{break-inside:avoid}tbody.g.closed tr:not(.grp){display:table-row}
tbody.g.closed tr.det:not(.open){display:none}.garr,.sarr{display:none}h2.sth.closed+.secbody{display:block}.tog{display:none}}
"""

STATUS_COLORS = {"Разработка": "#2457d6", "Регистрация и постановка": "#7048e8", "Проектирование": "#0c8599",
                 "На инициации": "#e8890c", "Планируется": "#e8890c", "Приостановлен": "#f76707",
                 "Завершен": "#0f9d58", "Отказ": "#868e96"}
FALLBACK_COLORS = ["#2457d6", "#0f9d58", "#e8890c", "#7048e8", "#e03131", "#0c8599", "#d6336c", "#5c940d", "#f76707"]

SCRIPT = """<script>
function tg(r){var d=r.nextElementSibling;r.classList.toggle('open');d.classList.toggle('open');}
function gkey(b){var t=b.closest('table');return 'grp:'+location.pathname+':'+t.dataset.closed+':'+b.dataset.g;}
function setGroup(b,c){b.classList.toggle('closed',c);try{c?sessionStorage.setItem(gkey(b),'1'):sessionStorage.removeItem(gkey(b));}catch(e){}}
function tgGroup(r){var b=r.parentNode;setGroup(b,!b.classList.contains('closed'));}
function allGroups(c){document.querySelectorAll('tbody.g').forEach(function(b){setGroup(b,c);});}
document.querySelectorAll('tbody.g').forEach(function(b){try{if(sessionStorage.getItem(gkey(b)))b.classList.add('closed');}catch(e){}});
document.addEventListener('keydown',function(ev){var r=ev.target.closest&&ev.target.closest('tr.grp');
  if(r&&!ev.target.closest('.notecell')&&(ev.key==='Enter'||ev.key===' ')){ev.preventDefault();tgGroup(r);}});
function skey(h){return 'sec:'+location.pathname+':'+h.dataset.sec;}
function setSec(h,c){h.classList.toggle('closed',c);try{c?sessionStorage.setItem(skey(h),'1'):sessionStorage.removeItem(skey(h));}catch(e){}}
function tgSec(ev,h){if(ev.target.closest('a'))return;setSec(h,!h.classList.contains('closed'));}
function allSecs(c){document.querySelectorAll('h2.sth').forEach(function(h){setSec(h,c);});}
document.querySelectorAll('h2.sth').forEach(function(h){try{if(sessionStorage.getItem(skey(h)))h.classList.add('closed');}catch(e){}});
function all(o){document.querySelectorAll('tr.main').forEach(function(r){r.classList.toggle('open',o);r.nextElementSibling.classList.toggle('open',o);});}
(function(){
var tip=document.createElement('div');tip.id='resTip';document.body.appendChild(tip);var hide=null,cur=null;
function mark(){document.querySelectorAll('.res').forEach(function(d){d.classList.toggle('cut',d.scrollHeight>d.clientHeight+2);});}
function show(d){clearTimeout(hide);if(cur===d)return;cur=d;
  tip.innerHTML='<div class="t"></div>';tip.firstChild.textContent=d.dataset.head||'';tip.appendChild(document.createTextNode(d.textContent));
  tip.style.display='block';var r=d.getBoundingClientRect(),w=tip.offsetWidth,h=tip.offsetHeight;
  var x=Math.max(8,Math.min(r.left-10,innerWidth-w-8)),y=r.bottom+6;if(y+h>innerHeight-8)y=Math.max(8,r.top-h-6);
  tip.style.left=x+'px';tip.style.top=y+'px';}
function later(){clearTimeout(hide);hide=setTimeout(function(){tip.style.display='none';cur=null;},200);}
document.addEventListener('mouseover',function(ev){var d=ev.target.closest&&ev.target.closest('.res.cut');
  if(d)show(d);else if(ev.target.closest&&ev.target.closest('#resTip'))clearTimeout(hide);else if(cur)later();});
addEventListener('scroll',function(ev){if(cur&&ev.target!==tip){tip.style.display='none';cur=null;}},true);
addEventListener('resize',mark);addEventListener('load',mark);mark();
})();
window.addEventListener('beforeprint',function(){document.querySelectorAll('details.phd').forEach(function(d){d.open=true;});});
</script>"""


def e(v):
    return escape("" if v is None else str(v))


def fmt_date(s):
    if not s:
        return "—"
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(s)


def fmt_dt(s):
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return s


def fmt_h(x):
    """1234.5 -> '1 234,5'"""
    x = float(x or 0)
    s = f"{x:,.1f}".replace(",", " ").replace(".", ",")
    return s[:-2] if s.endswith(",0") else s


def page(title, body, standalone=False):
    nav = "" if standalone else (
        '<header class="top"><b>Отчёты по проектам разработки</b>'
        '<a href="/">Проекты</a><a href="/reports">Архив отчётов</a></header>')
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body>{nav}<main>{body}</main>'
            f'{"" if standalone else ROW_LINK_SCRIPT}</body></html>')


# Кликабельные строки таблиц: <tr class="link" data-href="...">.
# Ссылки внутри строки работают как обычно; Ctrl/Cmd-клик и средняя кнопка открывают новую вкладку.
ROW_LINK_SCRIPT = """<script>
(function(){function go(ev){var tr=ev.target.closest('tr.link');if(!tr||ev.target.closest('a,button,input,select'))return;
var u=tr.dataset.href;if(ev.button===1||ev.ctrlKey||ev.metaKey){window.open(u,'_blank');ev.preventDefault();}
else if(ev.button===0){location.href=u;}}
document.addEventListener('click',go);document.addEventListener('auxclick',go);
document.addEventListener('keydown',function(ev){var tr=ev.target.closest&&ev.target.closest('tr.link');
if(tr&&ev.key==='Enter')location.href=tr.dataset.href;});})();
</script>"""


def _lock_cell(r):
    if r.get("locked_at"):
        return f'<td><span class="pill ok" title="{e(r.get("locked_by"))}">🔒 зафиксирован</span></td>'
    return '<td><span class="pill warn">черновик</span></td>'


def _report_row_attrs(r):
    return f'class="link" tabindex="0" data-href="/reports/{r["id"]}" title="Открыть отчёт №{r["id"]}"'


def error_page(msg):
    return page("Ошибка", f'<div class="card err"><b>Ошибка.</b> {e(msg)}</div><a href="/">← К списку проектов</a>')


def status_badge(status):
    c = STATUS_COLORS.get(status, "#5d6b82")
    return f'<span class="badge" style="background:{c}1f;color:{c};font-weight:600">{e(status) or "—"}</span>'


# --- список проектов --------------------------------------------------------
def projects_page(projects, show_all, manager):
    managers = sorted({p["manager"] for p in projects if p["manager"]})
    rows = [p for p in projects if not manager or p["manager"] == manager]
    opts = "".join(f'<option value="{e(m)}"{" selected" if m == manager else ""}>{e(m)}</option>' for m in managers)
    tr = "".join(
        f'<tr><td><a href="/projects/{e(p["code"])}">{e(p["code"])}</a></td>'
        f'<td><a href="/projects/{e(p["code"])}">{e(p["name"])}</a></td><td>{e(p["direction"])}</td>'
        f'<td>{e(p["manager"]) or "—"}</td><td>{status_badge(p["status"])}</td><td>{e(p["type"])}</td>'
        f'<td class="date">{fmt_dt(p["last_report"]) if p["last_report"] else "—"}'
        f'{f" <span class=muted>({p["reports_count"]})</span>" if p["reports_count"] else ""}</td></tr>'
        for p in rows)
    body = f"""
<h1>Проекты разработки</h1>
<p class="muted">Данные берутся из главного сервиса в режиме наблюдателя. Выберите проект, чтобы сформировать отчёт.</p>
<form class="inline card noprint" method="get">
 <label>Менеджер проекта<select name="manager"><option value="">Все</option>{opts}</select></label>
 <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" name="all" value="1" style="min-width:0"
 {"checked" if show_all else ""}> включая завершённые и отменённые</label>
 <button class="btn sec">Показать</button>
</form>
<div class="wrap"><table><thead><tr><th>ID</th><th>Проект</th><th>Продуктовое направление</th><th>Менеджер</th><th>Статус</th>
<th>Тип</th><th>Последний отчёт</th></tr></thead><tbody>{tr or '<tr><td colspan=7 class=empty>Нет проектов</td></tr>'}</tbody></table></div>"""
    return page("Проекты", body)


# --- карточка проекта ------------------------------------------------------
def project_page(info, reports, period_start, prev):
    hist = "".join(
        f'<tr {_report_row_attrs(r)}><td>Отчёт №{r["id"]}</td><td class="date">{fmt_dt(r["created_at"])}</td>'
        f'<td class="date">{fmt_date(r["period_start"])} — {fmt_date(r["created_at"])}</td><td>{e(r["author"])}</td>'
        f'{_lock_cell(r)}</tr>' for r in reversed(reports))
    if prev:
        period = (f'<p>Период отчёта будет начинаться с даты предыдущего отчёта: '
                  f'<b>{fmt_dt(prev["created_at"])}</b>.</p><input type="hidden" name="period_start" value="">')
    else:
        period = (f'<label>Начало отчётного периода (первый отчёт)'
                  f'<input type="date" name="period_start" value="{period_start.isoformat()}"></label>')
    body = f"""
<p class="noprint"><a href="/">← Все проекты</a></p>
<h1>{e(info["code"])} · {e(info["name"])}</h1>
<div class="card grid">
 <div>Продуктовое направление</div><div>{e(info["direction"])} {f'({e(info["niokr_direction"])})' if info["niokr_direction"] else ""}</div>
 <div>Менеджер проекта</div><div>{e(info["manager"]) or "—"}</div>
 <div>Статус</div><div>{status_badge(info["status"])}</div>
 <div>Тип проекта</div><div>{e(info["type"])}</div>
</div>
<h2>Сформировать отчёт</h2>
<form class="card" method="post" action="/projects/{e(info["code"])}/reports">
 {period}
 <div style="display:flex;gap:12px;align-items:end;flex-wrap:wrap">
 <label>Кто запрашивает отчёт<input name="author" required value="{e(info["manager"])}"></label>
 <button class="btn">Сформировать отчёт</button></div>
 <p class="lock">Сформированный отчёт сохраняется в архиве; зафиксированный отчёт изменить и удалить нельзя. До фиксации
 в нём можно обновить данные из главного сервиса, поправить результаты этапов, убрать лишние этапы, добавить примечания
 к этапам и к сводным группам подразделений; черновик можно удалить из архива.</p>
</form>
<h2>История отчётов</h2>
<table><thead><tr><th>Отчёт</th><th>Дата проведения</th><th>Период</th><th>Сформировал</th><th>Состояние</th></tr></thead>
<tbody>{hist or '<tr><td colspan=5 class=empty>Отчётов по проекту ещё нет</td></tr>'}</tbody></table>"""
    return page(f'{info["code"]} {info["name"]}', body)


# --- отчёт -----------------------------------------------------------------
def _pill_days(d, closed=False):
    if d is None:
        return ""
    if d == 0:
        return '<span class="pill ok">в срок</span>'
    if d > 0:
        return f'<span class="pill bad">+{d} дн.</span>'
    return f'<span class="pill early">{d} дн.</span>'


def _pill_months(d):
    if not d:
        return '<span class="pill ok">в срок</span>'
    if d > 0:
        return f'<span class="pill bad">+{d} мес.</span>'
    return f'<span class="pill early">{d} мес.</span>'


def _plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def elapsed(start: date, end: date):
    """Сколько прошло от start до end: '3 года 4 месяца 12 дней'."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    y, m = divmod(months, 12)
    anchor_y, anchor_m = divmod(start.month - 1 + months, 12)
    anchor_y += start.year
    anchor_m += 1
    day = min(start.day, [31, 29 if anchor_y % 4 == 0 and (anchor_y % 100 or anchor_y % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][anchor_m - 1])
    d = (end - date(anchor_y, anchor_m, day)).days
    parts = []
    if y:
        parts.append(f'{y} {_plural(y, "год", "года", "лет")}')
    if m:
        parts.append(f'{m} {_plural(m, "месяц", "месяца", "месяцев")}')
    if d or not parts:
        parts.append(f'{d} {_plural(d, "день", "дня", "дней")}')
    return " ".join(parts)


def _parse_any(s):
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s)[:10], fmt).date()
        except (TypeError, ValueError):
            pass
    return None


def _days_txt(n):
    return f'{n:,} {_plural(n, "день", "дня", "дней")}'.replace(",", "\u202f")


def _tile(color, label, big, small, big_color=None):
    style = f' style="color:{big_color}"' if big_color else ""
    return (f'<div class="kpi" style="--c:{color}"><div class="l">{label}</div>'
            f'<div class="v"{style}>{big}</div><div class="h">{small}</div></div>')


def _date_tile(color, label, value, report_date):
    d = _parse_any(value)
    end = _parse_any(report_date)
    if not d:
        return _tile(color, label, "дата не указана", "в главном сервисе дата не заполнена", "var(--muted)")
    if d > end:
        return _tile(color, label, f'через {elapsed(end, d)}', f'{d:%d.%m.%Y} · на дату отчёта')
    return _tile(color, label, elapsed(d, end),
                 f'с {d:%d.%m.%Y} · {_days_txt((end - d).days)} на дату отчёта')


def _target_tile(info, report_date, live=None):
    """Срок завершения разработки — только по «Дате МП» из дорожной карты главного сервиса.

    live — для отчётов, сформированных до появления этой плитки: Дата МП, полученная из главного
    сервиса в момент просмотра ({"ok": bool, "value": dev_deadline | None, "at": "ДД.ММ.ГГГГ"}).
    """
    label = "Срок завершения разработки"
    color = "#e8890c"
    end = _parse_any(report_date)
    done = _parse_any(info.get("dev_completed"))
    if done:
        return _tile("#0f9d58", label, "разработка завершена", f'{done:%d.%m.%Y}', "var(--ok)")
    if "dev_deadline" in info:
        dl = info["dev_deadline"]
    elif live and live.get("ok"):
        dl = live["value"]
    else:
        return _tile(color, label, "нет данных",
                     "срок не сохранялся в этом отчёте, а главный сервис сейчас недоступен", "var(--muted)")
    done = dl and dl.get("dev_done") and _parse_any(dl.get("dev_done_date"))
    if done:
        return _tile("#0f9d58", label, "разработка завершена", f'{done:%d.%m.%Y}', "var(--ok)")
    pick = deadline_pick((dl or {}).get("dates"))
    if not pick:
        return _tile(color, label, "не задан",
                     "в дорожной карте нет ни планируемой, ни желаемой даты, ни Даты МП", "var(--muted)")
    month, labels = pick
    y, m = int(month[:4]), int(month[5:7])
    pills = " ".join(f'<span class="pill {DEADLINE_PILL[x]}">{x}</span>' for x in labels)
    small = f'{pills} <b style="color:var(--ink)">{m:02d}.{y}</b>'
    last = date(y, m, calendar.monthrange(y, m)[1])
    if end <= last:
        return _tile(color, label, f'осталось {elapsed(end, last)}', small)
    return _tile("#e03131", label, f'просрочен на {elapsed(last, end)}', small, "var(--bad)")


DEADLINE_PILL = {"Планируемая дата": "dl-pl", "Дата МП": "dl-mp", "Желаемая дата": "dl-ds"}


class _Colors:
    def __init__(self, known):
        self.known = dict(known or {})
        self.i = 0

    def __call__(self, name):
        if name not in self.known:
            self.known[name] = FALLBACK_COLORS[self.i % len(FALLBACK_COLORS)]
            self.i += 1
        return self.known[name]


def _hours_cell(h):
    if not h or not h.get("total"):
        return '<td class="hrs muted">—</td>'
    per = f'<div class="p">+{fmt_h(h["period"])} ч за период</div>' if h.get("period") else ""
    return f'<td class="hrs"><b>{fmt_h(h["total"])}</b> ч{per}</td>'


def _detail(s, color, closed=False):
    h = s.get("hours") or {}
    rows = h.get("by_subdivision") or []
    if rows:
        mx = max(r["total"] for r in rows) or 1
        subs = "".join(
            f'<tr style="--c:{color(r["subdivision"])}"><td><span class="dot"></span>{e(r["subdivision"])}</td>'
            f'<td style="width:28%"><div class="bar" style="width:{r["total"] / mx * 100:.0f}%"></div></td>'
            f'<td class="num"><b>{fmt_h(r["total"])}</b></td>'
            f'<td class="num muted">{fmt_h(r["period"]) if r["period"] else "—"}</td></tr>' for r in rows)
        subs = (f'<table class="subs"><tr class="muted small"><td>Подразделение</td><td></td><td class="num">Всего, ч</td>'
                f'<td class="num">За период, ч</td></tr>{subs}'
                f'<tr class="tot"><td>Итого</td><td></td><td class="num">{fmt_h(h["total"])}</td>'
                f'<td class="num">{fmt_h(h["period"])}</td></tr></table>')
    else:
        subs = '<p class="empty">Трудозатрат по этапу нет</p>'
    orig = ""
    if s.get("edited"):
        orig = (f'<details class="small muted" style="margin-top:6px"><summary>текст изменён вручную · исходный из главного сервиса</summary>'
                f'<div class="pre">{e(s["original_description"]) or "—"}</div></details>')
    head = "Полученные результаты" if closed else "Планируемые результаты"
    return (f'<div class="det-grid"><div><h4>{head}</h4><div class="restxt">{e(s["description"]) or "—"}</div>{orig}</div>'
            f'<div><h4>Трудозатраты по подразделениям</h4>{subs}</div></div>')


def _img_src(img):
    if "data" in img:  # отдельный HTML-файл: изображение встраивается в страницу
        return f'data:{img["mime"]};base64,{base64.b64encode(img["data"]).decode("ascii")}'
    return f'/notes/images/{img["id"]}'


GROUP_PREFIX = "grp:"  # примечание к сводной группе подразделения
REPORT_SECTIONS = {"current": "current_stages", "closed": "closed_stages"}


def group_note_key(section, name):
    return f"{GROUP_PREFIX}{section}:{name}"


def _note_cell(key, name, note, editable):
    note = note or {"text": "", "images": [], "updated_at": None}
    text, imgs = note["text"], note["images"]
    thumbs = "".join(f'<a href="{_img_src(i)}" target="_blank" rel="noopener"><img src="{_img_src(i)}" alt=""></a>'
                     for i in imgs)
    body = ""
    if text:
        body += f'<div class="ntext">{e(text)}</div>'
    if thumbs:
        body += f'<div class="nimgs">{thumbs}</div>'
    if editable:
        data = json.dumps([{"id": i["id"], "url": _img_src(i)} for i in imgs])
        btn = ("✎ изменить" if (text or imgs) else "+ добавить")
        body += (f'<button type="button" class="nedit noprint" onclick="openNote(this)">{btn}</button>')
        kind = "group" if key.startswith(GROUP_PREFIX) else "stage"
        attrs = (f' data-vid="{e(key)}" data-name="{e(name)}" data-kind="{kind}" data-text="{e(text)}"'
                 f' data-images="{e(data)}"')
    else:
        attrs = ""
        body = body or '<span class="muted">—</span>'
    return f'<td class="notecell" onclick="event.stopPropagation()"{attrs}>{body}</td>'


NO_SUBDIVISION = "Подразделение не указано"


def group_by_subdivision(stages):
    """Этапы, сгруппированные по ответственному подразделению: [(подразделение, [этапы])].
    Группы — по алфавиту, «не указано» в конце; внутри группы порядок этапов сохраняется."""
    groups = {}
    for s in stages:
        groups.setdefault((s.get("subdivision") or "").strip() or NO_SUBDIVISION, []).append(s)
    return sorted(groups.items(), key=lambda kv: (kv[0] == NO_SUBDIVISION, kv[0].lower()))


def _group_row(name, items, note=None, editable=False, section="current"):
    total = sum((s.get("hours") or {}).get("total") or 0 for s in items)
    period = sum((s.get("hours") or {}).get("period") or 0 for s in items)
    hrs = f'{fmt_h(total)} ч' + (f' · +{fmt_h(period)} ч за период' if period else "") if total else "трудозатрат нет"
    n = len(items)
    note_cell = _note_cell(group_note_key(section, name), f"{name} — сводка по подразделению",
                           note, editable)
    return (f'<tr class="grp" onclick="tgGroup(this)" tabindex="0" title="Свернуть / развернуть группу">'
            f'<td colspan="5"><span class="garr">▾</span><span class="gname">{e(name)}</span>'
            f' <span class="gcnt">{n} {_plural(n, "этап", "этапа", "этапов")}</span>'
            f' <span class="ghrs">{hrs}</span></td>{note_cell}<td></td></tr>')


def _stage_rows(stages, color, closed, report_date, notes=None, editable=False):
    section = "closed" if closed else "current"
    out = []
    i = 0
    for name, items in group_by_subdivision(stages):
        out.append(f'<tbody class="g" data-g="{e(name)}">'
                   f'{_group_row(name, items, (notes or {}).get(group_note_key(section, name)), editable, section)}')
        for s in items:
            i += 1
            out.append(_stage_row(i, s, color, closed, report_date, notes or {}, editable))
        out.append('</tbody>')
    return "".join(out)


def _stage_row(i, s, color, closed, report_date, notes, editable):
    if closed:
        when = (f'<td class="date">{fmt_date(s["original_date"])} → <b>{fmt_date(s["fact_date"])}</b>'
                f'<div>{_pill_days(s["deviation_days"])}</div></td>')
    else:
        overdue = s["planned_date"] and s["planned_date"][:10] < report_date
        flag = '<span class="pill bad">просрочен</span>' if overdue else ""
        was = (f'<div class="was">был <s>{fmt_date(s["original_date"])}</s> · переносов {s["transfers"]} '
               f'{_pill_days(s["deviation_days"])}</div>') if s.get("transfers") else ""
        when = f'<td class="date"><b>{fmt_date(s["planned_date"])}</b> {flag}{was}</td>'
    ids = f' data-vid="{e(s["version_id"])}" data-name="{e(s["name"])}"'
    dele = (f'<div class="noprint"><button type="button" class="sdel"{ids} title="Удалить этап из отчёта"'
            f' onclick="event.stopPropagation();removeStage(this)">✕ удалить этап</button></div>') if editable else ""
    desc = (s.get("description") or "").strip()
    res = (f'<div class="res" data-head="{e(s["name"])}">{e(desc)}</div>' if desc
           else '<div class="res none">—</div>')
    if s.get("edited"):
        res += '<span class="edited" title="Текст результатов изменён вручную">изменено</span> '
    if editable:
        res += (f'<button type="button" class="nedit noprint" onclick="event.stopPropagation();openDesc(this)"'
                f'{ids} data-text="{e(s["description"])}" data-orig="{e(s.get("original_description", ""))}"'
                f' data-edited="{1 if s.get("edited") else 0}">✎ изменить</button>')
    return (
        f'<tr class="main" onclick="tg(this)"><td class="muted">{i}</td>'
        f'<td><div class="nm">{e(s["name"])}</div>{dele}</td>{when}{_hours_cell(s.get("hours"))}'
        f'<td>{res}</td>'
        f'{_note_cell(s["version_id"], s["name"], notes.get(s["version_id"]), editable)}<td class="tog">›</td></tr>'
        f'<tr class="det"><td colspan="7">{_detail(s, color, closed)}</td></tr>')


def apply_edits(stages, edits):
    """Применяет правки к этапам отчёта: (показываемые этапы, удалённые из отчёта)."""
    shown, removed = [], []
    for s in stages:
        ed = (edits or {}).get(s["version_id"]) or {}
        s = {**s, "original_description": s.get("description") or ""}
        if ed.get("description") is not None:
            s["description"], s["edited"] = ed["description"], True
        (removed if ed.get("removed") else shown).append(s)
    return shown, removed


def _removed_line(removed, editable):
    if not removed or not editable:
        return ""
    items = ", ".join(f'«{e(s["name"])}» <button type="button" data-vid="{e(s["version_id"])}"'
                      f' onclick="restoreStage(this)">вернуть</button>' for s in removed)
    return f'<div class="removed noprint">Удалены из отчёта: {items}</div>'


def _stage_table(stages, color, closed, report_date, notes=None, editable=False):
    if not stages:
        return '<div class="card empty">Нет этапов</div>'
    head = "Первоначальная → фактическая" if closed else "Срок"
    return (f'<div class="card stcard {"cl" if closed else "cu"}"><div class="wrap"><table class="stages" data-closed="{1 if closed else 0}"><thead><tr><th>№</th>'
            f'<th style="width:17%">Этап</th><th style="width:13%">{head}</th><th style="width:10%">Трудозатраты</th>'
            f'<th>{"Полученные результаты" if closed else "Планируемые результаты"}</th>'
            f'<th style="width:18%">Примечание</th><th></th></tr></thead>'
            f'{_stage_rows(stages, color, closed, report_date, notes, editable)}</table></div></div>')


NOTE_EDITOR = """
<dialog id="noteDlg" class="dlg noprint">
 <form method="dialog" onsubmit="return false">
  <h3>Примечание <span id="noteStage" class="muted"></span></h3>
  <textarea id="noteText" rows="7" placeholder="Текст примечания. Изображение можно вставить из буфера (Ctrl+V) или перетащить сюда."></textarea>
  <div id="noteImgs" class="dimgs"></div>
  <label class="upl">📎 Добавить изображение<input id="noteFile" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden></label>
  <div id="noteErr" class="nerr"></div>
  <div class="dbtns"><button type="button" class="btn sec" onclick="closeNote()">Закрыть</button>
  <button type="button" class="btn" onclick="saveNote()">Сохранить</button></div>
 </form>
</dialog>
<script>
(function(){
var dlg=document.getElementById('noteDlg'),ta=document.getElementById('noteText'),box=document.getElementById('noteImgs'),
    err=document.getElementById('noteErr'),cur=null,changed=false;
function base(){return '/reports/'+REPORT_ID+'/notes/'+encodeURIComponent(cur.vid);}
function render(){box.innerHTML='';cur.imgs.forEach(function(im){var d=document.createElement('div');d.className='dimg';
  d.innerHTML='<img src="'+im.url+'"><button type="button" title="Удалить">✕</button>';
  d.querySelector('button').onclick=function(){delImg(im.id);};box.appendChild(d);});}
function fail(m){err.textContent=m;}
function upload(file){if(!file||!/^image\\//.test(file.type)){fail('Можно добавлять только изображения');return;}
  fail('Загрузка…');fetch(base()+'/images',{method:'POST',headers:{'Content-Type':file.type},body:file})
  .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||r.status);return j;});})
  .then(function(j){cur.imgs.push({id:j.id,url:j.url});changed=true;fail('');render();})
  .catch(function(x){fail('Не удалось загрузить: '+x.message);});}
function delImg(id){if(!confirm('Удалить изображение из примечания?'))return;
  fetch(base()+'/images/'+id+'/delete',{method:'POST'}).then(function(r){if(!r.ok)throw new Error(r.status);
  cur.imgs=cur.imgs.filter(function(i){return i.id!==id;});changed=true;render();})
  .catch(function(x){fail('Не удалось удалить: '+x.message);});}
function reload(){try{sessionStorage.setItem('noteScroll',String(scrollY));}catch(e){}location.reload();}
window.openNote=function(btn){var td=btn.closest('td');cur={vid:td.dataset.vid,imgs:JSON.parse(td.dataset.images||'[]')};
  changed=false;ta.value=td.dataset.text||'';document.getElementById('noteStage').textContent='· '+td.dataset.name;
  ta.placeholder=td.dataset.kind==='group'
    ?'Примечание к сводке по подразделению: что сделано, что в работе, на что обратить внимание. Можно вставить изображение.'
    :'Текст примечания. Изображение можно вставить из буфера (Ctrl+V) или перетащить сюда.';
  fail('');render();dlg.showModal();ta.focus();};
window.closeNote=function(){dlg.close();if(changed)reload();};
window.saveNote=function(){fetch(base(),{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({text:ta.value})}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||r.status);});})
  .then(function(){dlg.close();reload();}).catch(function(x){fail('Не удалось сохранить: '+x.message);});};
document.getElementById('noteFile').onchange=function(){[].forEach.call(this.files,upload);this.value='';};
dlg.addEventListener('paste',function(ev){[].forEach.call(ev.clipboardData.items||[],function(it){
  if(it.kind==='file'&&/^image\\//.test(it.type)){ev.preventDefault();upload(it.getAsFile());}});});
dlg.addEventListener('dragover',function(ev){ev.preventDefault();});
dlg.addEventListener('drop',function(ev){ev.preventDefault();[].forEach.call(ev.dataTransfer.files,upload);});
dlg.addEventListener('cancel',function(ev){ev.preventDefault();closeNote();});
try{var y=sessionStorage.getItem('noteScroll');if(y){sessionStorage.removeItem('noteScroll');scrollTo(0,+y);}}catch(e){}
})();
</script>"""


STAGE_EDITOR = """
<dialog id="descDlg" class="dlg noprint">
 <form method="dialog" onsubmit="return false">
  <h3><span id="descHead">Результаты</span> <span id="descStage" class="muted"></span></h3>
  <textarea id="descText" rows="9"></textarea>
  <details class="orig"><summary>Исходный текст из главного сервиса</summary><div id="descOrig"></div></details>
  <div id="descErr" class="nerr"></div>
  <div class="dbtns"><button type="button" class="btn sec" id="descReset" onclick="saveDesc(true)" style="margin-right:auto">Вернуть исходный</button>
  <button type="button" class="btn sec" onclick="document.getElementById('descDlg').close()">Отмена</button>
  <button type="button" class="btn" onclick="saveDesc(false)">Сохранить</button></div>
 </form>
</dialog>
<dialog id="lockDlg" class="dlg noprint">
 <form method="post" action="/reports/__ID__/lock">
  <h3>🔒 Зафиксировать отчёт №__ID__</h3>
  <p class="warn"><b>Внимание: после фиксации версию отчёта изменить больше будет нельзя.</b><br>
  Станут недоступны обновление данных из главного сервиса, правка результатов, удаление и возврат этапов,
  изменение примечаний, а сам отчёт нельзя будет удалить.
  Отменить фиксацию невозможно.</p>
  <label>Кто фиксирует отчёт<input name="locked_by" required maxlength="200" value="__AUTHOR__"></label>
  <div class="dbtns"><button type="button" class="btn sec" onclick="document.getElementById('lockDlg').close()">Отмена</button>
  <button class="btn danger">Зафиксировать</button></div>
 </form>
</dialog>
<script>
(function(){
var dlg=document.getElementById('descDlg'),ta=document.getElementById('descText'),err=document.getElementById('descErr'),cur=null;
function url(vid,act){return '/reports/'+REPORT_ID+'/stages/'+encodeURIComponent(vid)+'/'+act;}
function reload(){try{sessionStorage.setItem('noteScroll',String(scrollY));}catch(e){}location.reload();}
function post(u,body){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})
  .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||r.status);return j;});});}
window.openDesc=function(b){cur=b.dataset;ta.value=cur.text||'';document.getElementById('descOrig').textContent=cur.orig||'—';
  document.getElementById('descStage').textContent='· '+cur.name;
  document.getElementById('descHead').textContent=b.closest('table').dataset.closed==='1'?'Полученные результаты':'Планируемые результаты';
  document.getElementById('descReset').style.display=cur.edited==='1'?'':'none';err.textContent='';dlg.showModal();ta.focus();};
window.saveDesc=function(reset){post(url(cur.vid,'description'),{text:reset?null:ta.value})
  .then(function(){dlg.close();reload();}).catch(function(x){err.textContent='Не удалось сохранить: '+x.message;});};
window.removeStage=function(b){if(!confirm('Удалить этап «'+b.dataset.name+'» из отчёта?\\n\\nДо фиксации отчёта этап можно будет вернуть.'))return;
  post(url(b.dataset.vid,'remove')).then(reload).catch(function(x){alert('Не удалось удалить этап: '+x.message);});};
window.restoreStage=function(b){post(url(b.dataset.vid,'restore')).then(reload).catch(function(x){alert('Не удалось вернуть этап: '+x.message);});};
window.openLock=function(){document.getElementById('lockDlg').showModal();};
})();
</script>"""

LOCKED_TOAST = """<div class="toast noprint" id="lockToast" role="alert"><div>🔒</div><div><b>Отчёт зафиксирован</b>
Версию изменить больше будет нельзя: результаты, состав этапов и примечания закрыты для правки.</div>
<button type="button" title="Закрыть" onclick="this.parentNode.remove()">✕</button></div>
<script>history.replaceState(null,'',location.pathname);
setTimeout(function(){var t=document.getElementById('lockToast');if(t)t.remove();},12000);</script>"""

UPDATED_TOAST = """<div class="toast noprint" id="updToast" role="alert" style="background:#0b3f8c"><div>⟳</div>
<div><b>Данные обновлены из главного сервиса</b>
Отчёт пересобран по актуальным данным. Примечания, изменённые результаты и удалённые этапы сохранены.</div>
<button type="button" title="Закрыть" onclick="this.parentNode.remove()">✕</button></div>
<script>history.replaceState(null,'',location.pathname);
setTimeout(function(){var t=document.getElementById('updToast');if(t)t.remove();},12000);</script>"""

REFRESH_DIALOG = """
<dialog id="refreshDlg" class="dlg noprint">
 <form method="post" action="/reports/__ID__/refresh" id="refreshForm">
  <h3>⟳ Обновить данные из главного сервиса</h3>
  <p>Отчёт будет заново собран по актуальным данным главного сервиса: статус и сроки проекта,
  ключевые точки, состав, сроки и результаты этапов, трудозатраты, срок завершения разработки.</p>
  <p class="warn"><b>Дата отчёта и отчётный период не изменятся</b> — обновляются только данные,
  которые берутся из главного сервиса.</p>
  <p>Сохранятся: <b>примечания</b> (с изображениями) к этапам и сводным группам, <b>изменённый текст
  результатов</b> и <b>удалённые этапы</b>.</p>
  <div class="dbtns"><button type="button" class="btn sec" onclick="document.getElementById('refreshDlg').close()">Отмена</button>
  <button class="btn" id="refreshGo">Обновить данные</button></div>
 </form>
</dialog>
<script>
window.openRefresh=function(){document.getElementById('refreshDlg').showModal();};
document.getElementById('refreshForm').addEventListener('submit',function(){
  var b=document.getElementById('refreshGo');b.disabled=true;b.textContent='Обновление…';});
</script>"""


def _project_hours_section(ph, color, period_start, report_date):
    if not ph:
        return ('<h2>Трудозатраты по проекту</h2><div class="card empty">Нет данных о трудозатратах '
                '(в отчёт не сохранялись, главный сервис недоступен)</div>')
    since = f'учёт с {fmt_date(ph["since"])}' if ph.get("since") else "списаний нет"
    return f"""<h2>Трудозатраты по проекту</h2>
<div class="card phcard">
 <div class="phgrid">
  <div class="ph" style="--c:#2457d6"><div class="l">Всего по проекту</div><div class="v">{fmt_h(ph["total"])} ч</div>
   <div class="h">{since} по {fmt_date(report_date)}</div>
   {_subs_details(ph["by_subdivision"], "total", color)}</div>
  <div class="ph" style="--c:#0f9d58"><div class="l">За отчётный период</div><div class="v">{fmt_h(ph["period"])} ч</div>
   <div class="h">{fmt_date(period_start)} — {fmt_date(report_date)}</div>
   {_subs_details(ph["by_subdivision"], "period", color)}</div>
 </div>
</div>"""


def _subs_details(by_subdivision, key, color):
    """Раскрывающаяся разбивка часов по подразделениям: key = "total" или "period"."""
    rows = sorted((r for r in by_subdivision if r[key] > 0), key=lambda r: (-r[key], r["subdivision"]))
    if not rows:
        return '<div class="small muted" style="margin-top:10px">Списаний нет</div>'
    total = sum(r[key] for r in rows)
    mx = rows[0][key]
    trs = "".join(
        f'<tr style="--c:{color(r["subdivision"])}"><td><span class="dot"></span>{e(r["subdivision"])}</td>'
        f'<td style="width:26%"><div class="bar" style="width:{r[key] / mx * 100:.0f}%"></div></td>'
        f'<td class="num"><b>{fmt_h(r[key])}</b></td><td class="num muted">{r[key] / total * 100:.0f}%</td></tr>'
        for r in rows)
    return (f'<details class="phd"><summary>По подразделениям <span class="muted">({len(rows)})</span></summary>'
            f'<table class="subs"><tr class="muted small"><td>Подразделение</td><td></td><td class="num">Часы</td>'
            f'<td class="num">Доля</td></tr>{trs}<tr class="tot"><td>Итого</td><td></td>'
            f'<td class="num">{fmt_h(total)}</td><td class="num">100%</td></tr></table></details>')


def report_page(rep, ok_hash, standalone=False, live_deadline=None, notes=None, live_hours=None,
                edits=None, lock=None, flash=None, prev_exists=True):
    p = rep["payload"]
    info = p["project"]
    report_date = rep["created_at"][:10]
    now_ym = report_date[:7]
    color = _Colors(p.get("subdivision_colors"))
    up, cm = p["upcoming_milestones"], p["closed_milestones"]
    cur, cur_removed = apply_edits(p["current_stages"], edits)
    cls, cls_removed = apply_edits(p["closed_stages"], edits)
    editable = not standalone and not lock
    editor = ""
    if editable:
        editor = (f'<script>var REPORT_ID={int(rep["id"])};</script>{NOTE_EDITOR}'
                  + STAGE_EDITOR.replace("__ID__", str(int(rep["id"]))).replace("__AUTHOR__", e(rep["author"]))
                  + REFRESH_DIALOG.replace("__ID__", str(int(rep["id"]))))
    lock_html = (f'<div class="lockst" title="Версию отчёта изменить нельзя">🔒 Зафиксирован '
                 f'{fmt_dt(lock["locked_at"])} · {e(lock["locked_by"])}</div>') if lock else (
        '<div class="lockst draft">черновик — отчёт не зафиксирован</div>' if standalone else
        '<div class="lockst draft">✎ Не зафиксирован — можно корректировать</div>')
    toast = LOCKED_TOAST if flash == "locked" and not standalone else ""
    if flash == "updated" and not standalone:
        toast += UPDATED_TOAST
    if "project_hours" in p:
        ph = p["project_hours"]
    elif live_hours:
        ph = live_hours[0]
        color = _Colors({**live_hours[1], **(p.get("subdivision_colors") or {})})
    else:
        ph = None
    hours_html = _project_hours_section(ph, color, rep["period_start"], rep["created_at"][:10])

    # ключевые точки
    up_html = "".join(
        f'<li><span class="when{" now" if f"{m["year"]}-{m["month"]:02d}" == now_ym else ""}">'
        f'{m["month"]:02d}.{m["year"]}</span><span class="nm">{e(m["name"])}'
        f'{f" <span class=muted>· {e(m["comment"])}</span>" if m["comment"] else ""}</span></li>' for m in up)
    cm_html = "".join(
        f'<li><span class="nm">{e(m["name"])}{f" <span class=muted>· {e(m["comment"])}</span>" if m["comment"] else ""}</span>'
        f'<span class="pf">{m["plan_month"]:02d}.{m["plan_year"]} → <b>{m["fact_month"]:02d}.{m["fact_year"]}</b></span>'
        f'{_pill_months(m["deviation_months"])}</li>' for m in cm)

    kpi_html = (_date_tile("#2457d6", "С открытия проекта", info.get("opened"), report_date)
                + _date_tile("#0f9d58", "С начала работ", info.get("work_started"), report_date)
                + _target_tile(info, report_date, live_deadline))

    prev_txt = (f'№{p["previous_report_id"]}' if p.get("previous_report_id") else "первый отчёт")
    if p.get("previous_report_id") and not standalone and prev_exists:
        prev_txt = f'<a style="color:#fff" href="/reports/{p["previous_report_id"]}">{prev_txt}</a>'
    sc = STATUS_COLORS.get(info["status"], "#2457d6")
    actions = "" if standalone else f"""
<div class="toolbar noprint"><a href="/projects/{e(info["code"])}">← К проекту</a>
<a href="/reports">Архив отчётов</a>
<a class="btn sec" href="javascript:window.print()">Печать / PDF</a>
<a class="btn sec" href="/reports/{rep["id"]}/download">Скачать HTML</a>
<a class="btn sec" href="/reports/{rep["id"]}.json">JSON</a>
{'<button type="button" class="btn sec" onclick="openRefresh()" title="Пересобрать отчёт по актуальным данным главного сервиса">⟳ Обновить данные</button>' if editable else ""}
{'<button type="button" class="btn lockbtn" onclick="openLock()">🔒 Зафиксировать отчёт</button>' if editable else ""}</div>"""

    body = f"""{actions}
<div class="hero">
 <div><span class="code">{e(info["id"])}</span> <span class="sub">Отчёт №{rep["id"]}</span>
  <h1>{e(info["name"])}</h1>
  <div class="meta"><span>Направление: <b>{e(info["direction"])}{f" ({e(info['niokr_direction'])})" if info["niokr_direction"] else ""}</b></span>
  <span>Тип: <b>{e(info["type"])}</b></span><span>Менеджер: <b>{e(info["manager"]) or "—"}</b></span></div>
 </div>
 <div class="right"><span class="status" style="color:{sc}">● {e(info["status"]) or "—"}</span>
  <div class="date">{fmt_dt(rep["created_at"])}</div>
  <div class="sub">период {fmt_date(rep["period_start"])} — {fmt_date(rep["created_at"])}</div>
  <div class="sub">предыдущий: {prev_txt} · сформировал: {e(rep["author"])}</div>
  {lock_html}</div>
</div>

<div class="kpis">{kpi_html}</div>

<h2>Ключевые точки</h2>
<div class="cols">
 <div class="card" style="--c:#2457d6"><h3>Актуальные · {len(up)}</h3>
  {f'<ul class="mlist">{up_html}</ul>' if up else '<p class="empty" style="padding:10px 14px">Нет актуальных ключевых точек</p>'}</div>
 <div class="card" style="--c:#0f9d58"><h3>Закрыты с предыдущего отчёта · {len(cm)} <span style="font-weight:400;opacity:.85">(план → факт)</span></h3>
  {f'<ul class="mlist">{cm_html}</ul>' if cm else '<p class="empty" style="padding:10px 14px">За период ключевые точки не закрывались</p>'}</div>
</div>

{toast}
<h2 class="sth" style="--sc:#0f9d58" data-sec="closed" onclick="tgSec(event,this)" title="Свернуть / развернуть этапы">
 <span class="sarr">▾</span>Этапы, закрытые с предыдущего отчёта <span class="cnt" style="background:var(--ok)">{len(cls)}</span>
 <span class="noprint" style="margin-left:auto;font-weight:400;font-size:13px">
 разделы: <a href="javascript:allSecs(false)">развернуть</a> · <a href="javascript:allSecs(true)">свернуть</a>
 &nbsp;|&nbsp; группы: <a href="javascript:allGroups(false)">развернуть</a> · <a href="javascript:allGroups(true)">свернуть</a>
 &nbsp;|&nbsp; этапы: <a href="javascript:all(true)">развернуть все</a> · <a href="javascript:all(false)">свернуть</a></span></h2>
<div class="secbody">{_stage_table(cls, color, True, report_date, notes, editable)}
{_removed_line(cls_removed, editable)}</div>

<h2 class="sth" style="--sc:#2457d6" data-sec="current" onclick="tgSec(event,this)" title="Свернуть / развернуть этапы">
 <span class="sarr">▾</span>Текущие этапы <span class="cnt">{len(cur)}</span></h2>
<div class="secbody">{_stage_table(cur, color, False, report_date, notes, editable)}
{_removed_line(cur_removed, editable)}</div>

{hours_html}

<p class="note">Нажмите на строку этапа, чтобы увидеть полный текст результатов и трудозатраты по подразделениям.
Трудозатраты «за период» — по неделям, начиная с даты начала периода. План ключевой точки — срок при её первом
появлении в отчётах сервиса, факт — срок в главном сервисе на дату отчёта.</p>
<p class="lock">Источник: {e(p["source"])} · Данные из главного сервиса хранятся в архиве без изменений; зафиксированный отчёт
изменить и удалить нельзя · контрольная сумма {e(rep["payload_sha256"][:16])}… {"✔ целостность подтверждена" if ok_hash else "✖ НАРУШЕНА ЦЕЛОСТНОСТЬ"}
· {f"отчёт зафиксирован {fmt_dt(lock['locked_at'])}: результаты, состав этапов и примечания больше не меняются"
   if lock else "до фиксации можно обновить данные из главного сервиса, править результаты этапов, удалять этапы "
                "из отчёта, вести примечания и удалить черновик"}</p>
{SCRIPT}{editor}"""
    return page(f'Отчёт №{rep["id"]} {info["code"]}', body, standalone=standalone)


# --- архив -------------------------------------------------------------------
def _size(n):
    return f"{n / 1024 / 1024:.1f} МБ".replace(".", ",") if n >= 1024 * 1024 else f"{max(1, n // 1024)} КБ"


def _backup_block(b):
    if not b:
        return ""
    last = b["last"]
    if last:
        age = datetime.now() - last["created"]
        stale = b["interval"] > 0 and age.total_seconds() > b["interval"] * 3600 * 1.5
        state = (f'<span class="pill {"bad" if stale else "ok"}">{"устарела" if stale else "актуальна"}</span> '
                 f'последняя: <b>{last["created"]:%d.%m.%Y %H:%M}</b> ({_size(last["size"])})')
    else:
        state = '<span class="pill bad">копий нет</span>'
    every = f'автоматически каждые {b["interval"]:g} ч' if b["interval"] > 0 else "автоматические копии выключены"
    flash = f'<div class="small" style="color:var(--ok);margin-top:4px">✔ {e(b["flash"])}</div>' if b.get("flash") else ""
    if b.get("flash") and "Не удалось" in b["flash"]:
        flash = f'<div class="small" style="color:var(--bad);margin-top:4px">✖ {e(b["flash"])}</div>'
    err = (f'<div class="small" style="color:var(--bad);margin-top:4px">Ошибка автоматической копии: {e(b["error"])}</div>'
           if b.get("error") else "")
    return f"""<div class="card noprint backup">
 <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
  <div><b>Резервные копии</b> · {state}
   <div class="small muted">{every}, хранятся последние {b["keep"]} (сейчас {b["count"]}) · папка: {e(b["dir"])}</div>
   {flash}{err}</div>
  <form method="post" action="/backups"><button class="btn sec">Создать копию сейчас</button></form>
 </div>
</div>"""


DELETE_DIALOG = """
<dialog id="delDlg" class="dlg noprint">
 <form method="post" action="" id="delForm">
  <h3>Удалить черновик отчёта?</h3>
  <p class="warn"><b>Действие необратимо.</b> <span id="delWhat">Отчёт</span> будет удалён вместе с
  примечаниями, изображениями и правками этапов. Восстановить его можно только из резервной копии базы.</p>
  <p class="small muted">Зафиксированный отчёт удалить нельзя — он остаётся в архиве навсегда.
  Если отчёт уже зафиксирован, удаление будет отклонено.</p>
  <div class="dbtns"><button type="button" class="btn sec" onclick="document.getElementById('delDlg').close()">Отмена</button>
  <button class="btn danger">Удалить отчёт</button></div>
 </form>
</dialog>
<script>
window.askDelete=function(b){
  document.getElementById('delWhat').textContent=b.dataset.label;
  document.getElementById('delForm').action='/reports/'+b.dataset.id+'/delete';
  document.getElementById('delDlg').showModal();};
</script>"""


def reports_page(reports, projects, selected="", backup=None, deleted=None):
    opts = "".join(
        f'<option value="{e(code)}"{" selected" if code == selected else ""}>{e(code)} · {e(name)} ({cnt})</option>'
        for code, name, cnt in projects)
    reset = ' <a href="/reports">Сбросить</a>' if selected else ""
    filt = f"""<form class="inline card noprint" method="get">
 <label>Проект<select name="project" onchange="this.form.submit()"><option value="">Все проекты</option>{opts}</select></label>
 <button class="btn sec">Показать</button>{reset}
</form>"""
    def _del_cell(r):
        if r.get("locked_at"):
            return '<td class="noprint"></td>'
        label = f'Отчёт №{r["id"]} от {fmt_dt(r["created_at"])} по проекту {r["project_code"]}'
        return (f'<td class="noprint"><button type="button" class="sdel" data-id="{r["id"]}"'
                f' data-label="{e(label)}" title="Удалить черновик отчёта"'
                f' onclick="event.stopPropagation();askDelete(this)">✕ удалить</button></td>')
    tr = "".join(
        f'<tr {_report_row_attrs(r)}><td>№{r["id"]}</td><td class="date">{fmt_dt(r["created_at"])}</td>'
        f'<td>{e(r["project_code"])} {e(r["project_name"])}</td>'
        f'<td class="date">{fmt_date(r["period_start"])}</td><td>{e(r["author"])}</td>{_lock_cell(r)}'
        f'{_del_cell(r)}</tr>' for r in reports)
    flash = (f'<div class="card" style="border-color:#b7e4c7;background:var(--ok-soft);color:#0b5c34">'
             f'✔ Черновик отчёта №{e(deleted)} удалён вместе с примечаниями и правками этапов.</div>') if deleted else ""
    body = f"""<h1>Архив отчётов</h1>
<p class="muted">Все сформированные отчёты. Черновик можно удалить; зафиксированный отчёт изменить и удалить нельзя.</p>
{flash}{filt}
<p class="muted small">Найдено отчётов: {len(reports)}</p>
<div class="wrap"><table><thead><tr><th>Отчёт</th><th>Дата проведения</th><th>Проект</th><th>Период с</th><th>Сформировал</th>
<th>Состояние</th><th></th></tr></thead>
<tbody>{tr or '<tr><td colspan=7 class=empty>Отчётов пока нет</td></tr>'}</tbody></table></div>
<div style="margin-top:18px">{_backup_block(backup)}</div>
{DELETE_DIALOG}"""
    return page("Архив отчётов", body)
