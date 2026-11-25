"""Настройки сервиса. Все значения можно переопределить переменными окружения."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Главный сервис (только чтение)
MAIN_URL = os.environ.get("MAIN_URL", "http://ryzhov-as.neurosoft.ru:8501").rstrip("/")
MAIN_API = MAIN_URL + "/api/v1"
# Ходить к главному сервису напрямую, минуя корпоративный прокси
MAIN_NO_PROXY = os.environ.get("MAIN_NO_PROXY", "1") == "1"
MAIN_TIMEOUT = int(os.environ.get("MAIN_TIMEOUT", "90"))

# Хранилище отчётов
DB_PATH = Path(os.environ.get("REPORT_DB", BASE_DIR / "data" / "reports.sqlite3"))

# Веб-сервер
HOST = os.environ.get("REPORT_HOST", "0.0.0.0")
PORT = int(os.environ.get("REPORT_PORT", "8600"))

# Период «с предыдущего отчёта» для самого первого отчёта по проекту (дней назад)
FIRST_REPORT_DEFAULT_DAYS = int(os.environ.get("FIRST_REPORT_DAYS", "30"))

# Резервные копии базы: папка (лучше — сетевая, на другом компьютере), периодичность и сколько хранить
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", BASE_DIR / "data" / "backups"))
BACKUP_INTERVAL_HOURS = float(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "30"))

# Примечания к этапам: максимальный размер изображения (МБ) и длина текста (символов)
NOTE_IMAGE_MAX_MB = int(os.environ.get("NOTE_IMAGE_MAX_MB", "10"))
NOTE_TEXT_MAX = int(os.environ.get("NOTE_TEXT_MAX", "20000"))

# Статусы проектов, которые показываются в списке по умолчанию
INACTIVE_STATUSES = {"Отказ", "Завершен"}
