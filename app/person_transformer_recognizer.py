"""
Распознаватель ФИО (PERSON) на дообученном ruBERT (token-classification).

Единственный распознаватель PERSON в модуле — запасного нет. Активен ТОЛЬКО если:
  - задан путь к обученной модели (env PERSON_MODEL_DIR), и
  - по этому пути лежит сохранённая transformers-модель, и
  - установлен пакет transformers.
Если модели нет, ФИО не распознаются вообще, и сервис отказывается стартовать
(см. app/main.py) — кроме явного ALLOW_NO_PERSON_MODEL=true для тестов и CI.

Импорт transformers — ленивый (внутри load), чтобы отсутствие пакета не
ломало запуск сервиса.
"""

import logging
import os

from presidio_analyzer import EntityRecognizer, RecognizerResult

from app.config import settings

logger = logging.getLogger(__name__)

# Путь к дообученной модели (папка с config.json/pytorch_model.bin или safetensors).
# Приоритет: env-переменная PERSON_MODEL_DIR (Docker/скрипты оценки) ->
# значение из .env через pydantic settings (постоянная конфигурация сервиса).
# Если env-переменная ЗАДАНА (даже пустой строкой) — она перебивает .env.
# Пустая строка => модель принудительно отключена. Это нужно, например, для
# честной оценки базовой линии, когда путь прописан в .env.
_env_model_dir = os.environ.get("PERSON_MODEL_DIR")
PERSON_MODEL_DIR = (
    _env_model_dir if _env_model_dir is not None else settings.person_model_dir
).strip()


def person_model_available() -> bool:
    """Есть ли по PERSON_MODEL_DIR валидная папка с моделью."""
    return bool(PERSON_MODEL_DIR) and os.path.isfile(
        os.path.join(PERSON_MODEL_DIR, "config.json")
    )


class PersonTransformerRecognizer(EntityRecognizer):
    """PERSON на дообученном ruBERT. Возвращает символьные спаны для Presidio."""

    def __init__(self, model_dir: str | None = None, default_score: float = 0.85):
        # Атрибуты ставим ДО super().__init__: в новых версиях presidio
        # EntityRecognizer.__init__ сам вызывает self.load(), которому нужен model_dir.
        self.model_dir = (model_dir or PERSON_MODEL_DIR).strip()
        self.default_score = default_score
        self._pipe = None
        super().__init__(
            supported_entities=["PERSON"],
            supported_language="ru",
            name="PersonTransformerRecognizer",
        )

    def load(self) -> None:
        if not self.model_dir or not os.path.isfile(
            os.path.join(self.model_dir, "config.json")
        ):
            logger.warning(
                "PersonTransformerRecognizer: модель не найдена (%r) — распознаватель неактивен",
                self.model_dir,
            )
            return
        try:
            from transformers import (
                AutoModelForTokenClassification,
                AutoTokenizer,
                pipeline,
            )

            tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
            model = AutoModelForTokenClassification.from_pretrained(self.model_dir)
            self._pipe = pipeline(
                "token-classification",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
            )
            logger.info(
                "PersonTransformerRecognizer: модель загружена из %s", self.model_dir
            )
        except Exception as exc:  # noqa: BLE001 — не роняем сервис из-за модели
            logger.error(
                "PersonTransformerRecognizer: не удалось загрузить модель: %s", exc
            )
            self._pipe = None

    def _ensure_loaded(self) -> None:
        if self._pipe is None:
            self.load()

    def analyze(self, text, entities, nlp_artifacts=None):
        if "PERSON" not in entities:
            return []
        self._ensure_loaded()
        if self._pipe is None:
            return []

        results = []
        for ent in self._pipe(text):
            group = ent.get("entity_group") or ent.get("entity") or ""
            # Разные схемы меток: наши дообученные модели дают PERSON, публичные
            # русские ru-NER (для сравнительных прогонов) — PER/B-PER. Оба -> PERSON.
            tail = group.rsplit("-", 1)[-1].upper()
            if tail in ("PERSON", "PER"):
                results.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=int(ent["start"]),
                        end=int(ent["end"]),
                        score=float(ent.get("score", self.default_score)),
                    )
                )
        return results
