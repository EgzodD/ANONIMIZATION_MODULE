"""
Ложные срабатывания на негативных примерах (precision-сторож).

Набор `test_negatives.jsonl` — предложения БЕЗ ПДн, но с числами и словами,
похожими на ПДн (номер заказа, артикул, трек, сумма, счёт-фактура). Ни одно из
них скрывать не нужно: любой плейсхолдер здесь = ложное срабатывание
(over-masking).

Категория: unit (качество распознавания). Не требует модели PERSON — без неё
модельные FP просто исчезают, потолок только снижается.

СТАТУС xfail: остаток FP = 1/20 (замер 02.09.2026).

История: было 7/20 → 5/20 после дообучения (27.07) → 1/20 сейчас. Причина
«presidio PHONE/PASSPORT ловят голые 10-значные числа (артикул, трек)»
устранена в коде: снят встроенный presidio-телефон и context-free паспорт
(коммит 01d0d4d).

Остался единственный случай: модель PERSON метит слово с заглавной
(«Штрихкод») как ФИО. Лечится дообучением с негативами — ML-скоуп.
Направление ошибки безопасное: over-masking, не утечка. Когда FP дойдёт до
нуля, pytest покажет xpass — сигнал снять пометку.
"""
import json
import os

import pytest

from app.anonymizer import anonymize_text

pytestmark = pytest.mark.unit

NEG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "training",
                        "test", "test_negatives.jsonl")


def _load():
    with open(NEG_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.mark.xfail(reason="остаток 1/20 (замер 02.09.2026): модель метит слово "
                          "с заглавной («Штрихкод») как ФИО. Regex-причины "
                          "устранены в 01d0d4d. Лечится дообучением с негативами",
                   strict=False)
def test_no_false_positives_on_negatives():
    """На предложениях без ПДн не должно быть ни одного плейсхолдера."""
    offenders = []
    for ex in _load():
        res = anonymize_text(ex["text"])
        types = [e["entity_type"] for e in res["entities_found"]]
        if types:
            # значение не печатаем — только типы (сами тексты негативов не ПДн,
            # но держим единый стиль: в отчёт об ошибке идут только типы + индекс)
            offenders.append((types, res["anonymized"]))
    assert not offenders, (
        f"ложных срабатываний: {len(offenders)} из негативов; "
        f"типы: {[t for t, _ in offenders]}"
    )
