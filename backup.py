"""Резервные копии базы отчётов из командной строки.

  python backup.py                 создать резервную копию сейчас
  python backup.py list            показать имеющиеся копии
  python backup.py restore <файл>  восстановить базу из копии (сервис должен быть остановлен)

Папка, периодичность и число хранимых копий — переменные BACKUP_DIR, BACKUP_INTERVAL_HOURS, BACKUP_KEEP.
"""
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from report_service import backup, config


def _service_running():
    try:
        with socket.create_connection(("127.0.0.1", config.PORT), timeout=1):
            return True
    except OSError:
        return False


def cmd_list():
    items = backup.list_backups()
    print(f"Папка: {config.BACKUP_DIR}")
    if not items:
        print("Резервных копий нет.")
    for b in items:
        print(f"  {b['created']:%d.%m.%Y %H:%M:%S}  {b['size'] / 1024 / 1024:7.2f} МБ  {b['path']}")


def cmd_restore(name):
    src = Path(name)
    if not src.exists():
        src = config.BACKUP_DIR / name
    if not src.exists():
        sys.exit(f"Файл копии не найден: {name}")
    if _service_running():
        sys.exit(f"Сервис работает на порту {config.PORT} — остановите его перед восстановлением.")
    conn = sqlite3.connect(src)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            sys.exit("Копия повреждена, восстановление отменено.")
        reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    finally:
        conn.close()
    db_path = Path(config.DB_PATH)
    if db_path.exists():  # текущая база сохраняется отдельно и при ротации копий не удаляется
        safe = config.BACKUP_DIR / f"before_restore_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as cur, sqlite3.connect(safe) as dst:
            cur.backup(dst)
        print(f"Текущая база сохранена: {safe}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src) as s, sqlite3.connect(db_path) as d:
        s.backup(d)
    print(f"База восстановлена из {src} (отчётов: {reports}). Запустите сервис: python run.py")


def main(argv):
    if not argv:
        print(f"Резервная копия создана: {backup.make_backup()}")
    elif argv[0] == "list":
        cmd_list()
    elif argv[0] == "restore" and len(argv) == 2:
        cmd_restore(argv[1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
