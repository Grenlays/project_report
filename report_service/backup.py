"""Резервные копии базы отчётов.

* Копия делается штатным механизмом SQLite (backup API) — корректно и во время работы сервиса.
* Сначала пишется во временный файл, проверяется (PRAGMA integrity_check) и только потом
  переименовывается в reports_ГГГГММДД_ЧЧММСС.sqlite3 — битых копий в папке не бывает.
* Хранятся последние BACKUP_KEEP копий, более старые удаляются (только файлы этого формата).
* Пока работает сервис, копия делается автоматически раз в BACKUP_INTERVAL_HOURS часов
  и сразу при запуске, если последняя копия старше этого срока.
"""
import logging
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import config

log = logging.getLogger("report_service.backup")
NAME_RE = re.compile(r"^reports_(\d{8}_\d{6})\.sqlite3$")
_lock = threading.Lock()


class BackupError(RuntimeError):
    pass


def _dir(backup_dir=None) -> Path:
    return Path(backup_dir or config.BACKUP_DIR)


def list_backups(backup_dir=None):
    """Копии от новых к старым: [{"path", "name", "created", "size"}]."""
    d = _dir(backup_dir)
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        m = NAME_RE.match(p.name)
        if m and p.is_file():
            out.append({"path": p, "name": p.name, "size": p.stat().st_size,
                        "created": datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")})
    return sorted(out, key=lambda b: b["created"], reverse=True)


def last_backup(backup_dir=None):
    items = list_backups(backup_dir)
    return items[0] if items else None


def make_backup(db_path=None, backup_dir=None, keep=None, now=None) -> Path:
    """Создаёт проверенную копию базы и удаляет лишние старые копии. Возвращает путь к копии."""
    src_path = Path(db_path or config.DB_PATH)
    if not src_path.exists():
        raise BackupError(f"База не найдена: {src_path}")
    d = _dir(backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    keep = config.BACKUP_KEEP if keep is None else keep
    with _lock:
        now = now or datetime.now()
        final = d / f"reports_{now:%Y%m%d_%H%M%S}.sqlite3"
        while final.exists():  # две копии в одну секунду
            now += timedelta(seconds=1)
            final = d / f"reports_{now:%Y%m%d_%H%M%S}.sqlite3"
        tmp = final.with_suffix(".tmp")
        try:
            src = sqlite3.connect(src_path)
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
                check = dst.execute("PRAGMA integrity_check").fetchone()[0]
                reports = dst.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            finally:
                dst.close()
                src.close()
            if check != "ok":
                raise BackupError(f"Копия не прошла проверку целостности: {check}")
            tmp.replace(final)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        removed = prune(d, keep)
    log.info("Резервная копия создана: %s (отчётов: %s, удалено старых копий: %s)", final, reports, removed)
    return final


def prune(backup_dir, keep) -> int:
    """Оставляет keep самых новых копий; возвращает число удалённых."""
    if keep <= 0:
        return 0
    old = list_backups(backup_dir)[keep:]
    for b in old:
        b["path"].unlink(missing_ok=True)
    return len(old)


def is_due(last, now=None, interval_hours=None) -> bool:
    interval = config.BACKUP_INTERVAL_HOURS if interval_hours is None else interval_hours
    if interval <= 0:
        return False
    now = now or datetime.now()
    return last is None or now - last["created"] >= timedelta(hours=interval)


class BackupScheduler(threading.Thread):
    """Фоновый поток сервиса: проверяет раз в 10 минут, не пора ли сделать копию."""

    def __init__(self, check_every_sec=600):
        super().__init__(name="backup-scheduler", daemon=True)
        self.check_every = check_every_sec
        self._halt = threading.Event()
        self.last_error = None

    def run(self):
        while not self._halt.is_set():
            try:
                if is_due(last_backup()):
                    make_backup()
                self.last_error = None
            except Exception as ex:  # ошибка копии не должна останавливать сервис
                self.last_error = f"{datetime.now():%d.%m.%Y %H:%M}: {ex}"
                log.error("Не удалось создать резервную копию: %s", ex)
            self._halt.wait(self.check_every)

    def stop(self):
        self._halt.set()
