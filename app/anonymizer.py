"""
Модуль анонимизации текста с Microsoft Presidio.
Настроен для русского языка с кастомными распознавателями.
"""

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine, DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig

from app.custom_recognizers import ALL_RU_RECOGNIZERS

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


def _build_analyzer() -> AnalyzerEngine:
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "ru", "model_name": "ru_core_news_sm"},
        ],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
    analyzer = AnalyzerEngine(
        nlp_engine=nlp_engine,
        supported_languages=["ru"],
    )
    for recognizer in ALL_RU_RECOGNIZERS:
        analyzer.registry.add_recognizer(recognizer)
    return analyzer


analyzer_engine = _build_analyzer()
anonymizer_engine = AnonymizerEngine()
deanonymizer_engine = DeanonymizeEngine()


def analyze_text(text: str) -> list:
    results = analyzer_engine.analyze(
        text=text,
        language="ru",
    )
    # Убираем LOCATION и другие исключённые типы
    return [r for r in results if r.entity_type not in EXCLUDED_ENTITIES]


def anonymize_text(text: str) -> dict:
    if not text or not text.strip():
        return {
            "original": text,
            "anonymized": text,
            "entities_found": [],
            "mapping": {},
        }

    results = analyze_text(text)

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
    for item in anonymized.items:
        original_value = text[item.start : item.end]
        if item.entity_type not in EXCLUDED_ENTITIES:
            mapping[item.text] = original_value

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


def anonymize_json(data, all_entities: list | None = None) -> tuple:
    """Рекурсивно анонимизирует все строковые значения в dict/list (для jsonb-полей)."""
    if all_entities is None:
        all_entities = []

    if data is None:
        return None, all_entities

    if isinstance(data, str):
        result = anonymize_text(data)
        all_entities.extend(result["entities_found"])
        return result["anonymized"], all_entities

    if isinstance(data, dict):
        anonymized_dict = {}
        for key, value in data.items():
            anonymized_dict[key], all_entities = anonymize_json(value, all_entities)
        return anonymized_dict, all_entities

    if isinstance(data, list):
        anonymized_list = []
        for item in data:
            anon_item, all_entities = anonymize_json(item, all_entities)
            anonymized_list.append(anon_item)
        return anonymized_list, all_entities

    return data, all_entities
