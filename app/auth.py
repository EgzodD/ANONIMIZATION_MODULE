"""
Аутентификация по API-ключу. Вынесена в отдельный модуль, чтобы её могли
использовать и ядро (app/main.py), и опциональные интеграции
(app/integrations/chatwoot/router.py) без циклических импортов.
"""

from fastapi import Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Depends(_api_key_header)):
    """Проверяет X-API-Key. Если API_KEY не задан в env — аутентификация отключена."""
    if settings.api_key and api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
