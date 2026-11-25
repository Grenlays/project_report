"""Клиент главного сервиса «Разработки».

Строго только чтение: разрешены GET-запросы и единственный POST — вход
наблюдателем (/auth/login-viewer), который ничего не меняет в данных.
Любой другой запрос клиент откажется отправлять.
"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import config

_ALLOWED_POST = {"/auth/login-viewer"}


class MainServiceError(RuntimeError):
    pass


class MainClient:
    def __init__(self, api_base: str = config.MAIN_API):
        self.api_base = api_base
        handlers = [urllib.request.ProxyHandler({})] if config.MAIN_NO_PROXY else []
        self._opener = urllib.request.build_opener(*handlers)
        self._token = None
        self._lock = threading.Lock()

    # --- низкоуровневые запросы -------------------------------------------
    def _request(self, method: str, path: str, params=None, auth=True):
        if method == "POST" and path not in _ALLOWED_POST:
            raise MainServiceError(f"Запрещённый запрос к главному сервису: {method} {path}")
        if method not in ("GET", "POST"):
            raise MainServiceError(f"Запрещённый метод: {method}")
        url = self.api_base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
        req.add_header("Accept", "application/json")
        if auth:
            req.add_header("Authorization", f"Bearer {self._get_token()}")
        try:
            with self._opener.open(req, timeout=config.MAIN_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and auth:
                raise _Unauthorized() from e
            body = e.read().decode("utf-8", "replace")[:300]
            raise MainServiceError(f"Главный сервис вернул {e.code} на {path}: {body}") from e
        except urllib.error.URLError as e:
            raise MainServiceError(f"Главный сервис недоступен ({path}): {e.reason}") from e

    def _get_token(self):
        with self._lock:
            if not self._token:
                data = self._request("POST", "/auth/login-viewer", auth=False)
                self._token = data.get("access_token")
                if not self._token:
                    raise MainServiceError("Не удалось войти в главный сервис как наблюдатель")
            return self._token

    def get(self, path: str, params=None):
        try:
            return self._request("GET", path, params)
        except _Unauthorized:
            with self._lock:
                self._token = None
            return self._request("GET", path, params)

    # --- предметные методы -----------------------------------------------
    def project_statuses(self):
        """Реестр проектов: ID, наименование, направление, тип, статус, менеджер."""
        return self.get("/portfolio/project-status")

    def milestones(self):
        """Ключевые точки всех проектов: project, name, month, year, comment."""
        return self.get("/portfolio/project-milestones")

    def stages(self):
        """Этапы (версии Redmine) с плановыми датами, результатами и признаком закрытия."""
        return self.get("/portfolio/calendar-events")

    def stage_date_changes(self, version_id: str):
        """История переносов плановой даты этапа."""
        return self.get(f"/portfolio/version-metadata/{urllib.parse.quote(str(version_id))}/date-changes")

    def project_detail(self, short_name: str):
        """Проект с этапами и трудозатратами сотрудников по неделям."""
        return self.get(f"/portfolio/projects/{urllib.parse.quote(short_name, safe='')}",
                        {"with_weekly": "true"})

    def roadmap(self):
        """Дорожная карта: по проектам — Дата МП, плановая/желаемая дата завершения разработки."""
        return self.get("/roadmap")

    def filters(self):
        """Справочники, в т.ч. manager_map (проект Redmine -> менеджер)."""
        return self.get("/portfolio/filters")


class _Unauthorized(Exception):
    pass
