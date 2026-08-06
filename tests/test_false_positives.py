"""
Ложные срабатывания на негативных примерах (precision-сторож).

Набор `test_negatives.jsonl` — предложения БЕЗ ПДн, но с числами и словами,
похожими на ПДн (номер заказа, артикул, трек, сумма, счёт-фактура). Ни одно из
них скрывать не нужно: любой плейсхолдер здесь = ложное срабатывание
(over-masking).

Категория: unit (качество распознавания). Не требует модели PERSON — без неё
модельные FP просто исчезают, потолок только снижается.

СТАТУС xfail: на текущей модели/распознавателях FP > 0 по двум причинам:
  1) presidio PHONE/PASSPORT ловят голые 10-значные числа (артикул, трек);
  2) модель PERSON метит частые слова с заглавной («Штрихкод», «Инвентарный»,
     «Талон») как ФИО.
Первое лечится правкой распознавателей, второе — дообучением с негативами
(план 27.07). Направление ошибки безопасное — over-masking, не утечка. Когда
FP дойдёт до нуля, pytest покажет xpass — сигнал снять пометку.
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


@pytest.mark.xfail(reason="остаток 5/20 после дообучения (27.07 снизило 7→5): "
                          "3 — regex presidio на голых числах (телефон/паспорт), "
                          "лечится распознавателями; 2 — модель ещё цепляет редкие "
                          "слова с заглавной (Штрихкод/Инвентарный)", strict=False)
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
