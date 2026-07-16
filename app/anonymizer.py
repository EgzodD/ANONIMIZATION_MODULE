"""
Модуль анонимизации текста с Microsoft Presidio.
Настроен для русского языка с кастомными распознавателями.
"""

import logging

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine, DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig

from app.custom_recognizers import ALL_RU_RECOGNIZERS

logger = logging.getLogger(__name__)

# Типы сущностей, которые НЕ надо скрывать (LOCATION по запросу)
EXCLUDED_ENTITIES = {"LOCATION", "NRP"}

# Операторы анонимизации для каждого типа
OPERATORS = {
    "PERSON": OperatorConfig("replace", {"new_value": "<PERSON>"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE>"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL>"}),
    "INN": OperatorConfig("replace", {"new_value": "<INN>"}),
    "SNILS": OperatorConfig("replace", {"new_value": "<SNILS>"}),
    "PASSPORT": OperatorConfig("replace", {"new_value": "<PASSPORT>"}),
    "DATE_OF_BIRTH": OperatorConfig("replace", {"new_value": "<DATE_OF_BIRTH>"}),
    "CREDIT_CARD": OperatorConfig("replace", {"new_value": "<CREDIT_CARD>"}),
    "DEFAULT": OperatorConfig("replace", {"new_value": "<PII>"}),
}


def _resolve_overlaps(results):
    """Оставляет непересекающиеся спаны — как presidio делает для текста.

    Одно значение (например число-ИНН) может ловиться сразу несколькими
    распознавателями (ИНН + телефон + паспорт). В анонимизированном ТЕКСТЕ
    presidio оставляет один спан (высший score), а вот mapping раньше строился
    по всем «сырым» результатам — и плейсхолдер затирался чужим значением
    (<PHONE> получал значение ИНН). Здесь берём тот же непересекающийся набор:
    сортировка по score убыв., при равенстве — длиннее; пересекающиеся с уже
    выбранными отбрасываем.
    """
    chosen = []
    for r in sorted(results, key=lambda x: (-x.score, -(x.end - x.start))):
        if any(not (r.end <= c.start or r.start >= c.end) for c in chosen):
            continue
        chosen.append(r)
    return chosen


def _build_analyzer() -> AnalyzerEngine:
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "ru", "model_name": "ru_core_news_lg"},
        ],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
    analyzer = AnalyzerEngine(
        nlp_engine=nlp_engine,
        supported_languages=["ru"],
    )
    for recognizer in ALL_RU_RECOGNIZERS:
        analyzer.registry.add_recognizer(recognizer)
        if hasattr(recognizer, "load"):
            recognizer.load()
    return analyzer


analyzer_engine = _build_analyzer()
anonymizer_engine = AnonymizerEngine()
deanonymizer_engine = DeanonymizeEngine()

# Политика: полный набор типов, которые сервис вообще имеет право скрывать
# (всё поддерживаемое минус безусловно исключённое). Кастомный параметр запроса
# может только СУЖАТЬ этот набор (отключать отдельные типы), но не расширять его.
POLICY_ENTITIES = frozenset(
    e for e in analyzer_engine.get_supported_entities(language="ru")
    if e not in EXCLUDED_ENTITIES
)


def resolve_disabled_entities(disable_entities) -> frozenset:
    """
    Приводит клиентский список отключаемых типов к безопасному множеству.

    Правила безопасности:
    - можно только СУЖАТЬ: отключить разрешено лишь типы из POLICY_ENTITIES;
    - неизвестные/запрещённые названия молча игнорируются (безопасное поведение —
      данные останутся скрытыми), но пишутся в лог как предупреждение;
    - факт отключения логируется (что именно отключили) для аудита.
    """
    if not disable_entities:
        return frozenset()

    requested = {str(x).strip().upper() for x in disable_entities if str(x).strip()}
    valid = frozenset(requested & POLICY_ENTITIES)
    ignored = requested - POLICY_ENTITIES

    if valid:
        logger.info("Кастомный параметр: отключены типы сущностей: %s", sorted(valid))
    if ignored:
        logger.warning(
            "Кастомный параметр: проигнорированы недопустимые типы (нет в политике): %s",
            sorted(ignored),
        )
    return valid


def analyze_text(text: str, disable_entities=None) -> list:
    disabled = resolve_disabled_entities(disable_entities)
    results = analyzer_engine.analyze(
        text=text,
        language="ru",
    )
    # Убираем LOCATION/исключённые типы, а также отключённые запросом типы
    return [
        r for r in results
        if r.entity_type not in EXCLUDED_ENTITIES and r.entity_type not in disabled
    ]


def anonymize_text(text: str, disable_entities=None) -> dict:
    if not text or not text.strip():
        return {
            "original": text,
            "anonymized": text,
            "entities_found": [],
            "mapping": {},
        }

    results = analyze_text(text, disable_entities=disable_entities)

    if not results:
        return {
            "original": text,
            "anonymized": text,
            "entities_found": [],
            "mapping": {},
        }

    anonymized = anonymizer_engine.anonymize(
        text=text,
        analyzer_results=results,
        operators=OPERATORS,
    )

    mapping = {}
    for result in _resolve_overlaps(results):
        if result.entity_type not in EXCLUDED_ENTITIES:
            original_value = text[result.start : result.end]
            op = OPERATORS.get(result.entity_type, OPERATORS["DEFAULT"])
            placeholder = op.params.get("new_value", f"<{result.entity_type}>")
            mapping[placeholder] = original_value

    entities_found = [
        {
            "entity_type": r.entity_type,
            "start": r.start,
            "end": r.end,
            "score": round(r.score, 2),
            "value": text[r.start : r.end],
        }
        for r in results
    ]

    return {
        "original": text,
        "anonymized": anonymized.text,
        "entities_found": entities_found,
        "mapping": mapping,
    }


def anonymize_json(data, all_entities: list | None = None, disable_entities=None) -> tuple:
    """Рекурсивно анонимизирует все строковые значения в dict/list (для jsonb-полей)."""
    if all_entities is None:
        all_entities = []

    if data is None:
        return None, all_entities

    if isinstance(data, str):
        result = anonymize_text(data, disable_entities=disable_entities)
        all_entities.extend(result["entities_found"])
        return result["anonymized"], all_entities

    if isinstance(data, dict):
        anonymized_dict = {}
        for key, value in data.items():
            anonymized_dict[key], all_entities = anonymize_json(
                value, all_entities, disable_entities=disable_entities
            )
        return anonymized_dict, all_entities

    if isinstance(data, list):
        anonymized_list = []
        for item in data:
            anon_item, all_entities = anonymize_json(
                item, all_entities, disable_entities=disable_entities
            )
            anonymized_list.append(anon_item)
        return anonymized_list, all_entities

    return data, all_entities
