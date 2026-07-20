"""
Регрессия приватности: LeakRate на held-out тест-сете.

Главная и единственная «сторожевая» метрика модуля обезличивания: ни одно
значение ПДн из эталона не должно остаться в анонимизированном тексте.
Пропуск = утечка = инцидент по 152-ФЗ. Тест падает при ЛЮБОМ ухудшении
приватности (смена/отключение модели PERSON, поломка распознавателя, регрессия
в anonymizer) — это и есть смысл метрики на постоянку (разовый 2×2-эксперимент
своё дело уже сделал, здесь остаётся только защита).

Логика LeakRate повторяет data/natasha_training/eval_2x2.py (value-based, по
оригинальному значению) — она координатно-независима и потому надёжна.

БЕЗОПАСНОСТЬ: в сообщениях об ошибке НЕ печатаются сами значения ПДн (это
де-анонимизирующие данные) — только счётчики, типы сущностей и номера примеров.
"""

import json
import os

import pytest

from app.anonymizer import anonymize_text
from app.person_transformer_recognizer import person_model_available

TEST_SET = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "natasha_training",
    "test",
    "test.jsonl",
)


def _load_examples():
    if not os.path.isfile(TEST_SET):
        pytest.skip(f"тест-сет не найден: {TEST_SET}")
    examples = []
    with open(TEST_SET, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


@pytest.mark.privacy
@pytest.mark.requires_model
class TestLeakRateRegression:
    """Порог приватности: 0 утечек ПДн на held-out тест-сете.

    Помечен requires_model: гейт имеет смысл только на продакшн-модели PERSON
    (дообученный ruBERT). Без модели распознавателя ФИО нет вообще, все имена
    утекут, и гейт упадёт не по делу — поэтому в CI без модели этот класс не
    запускается (см. pyproject.toml, .github/workflows/ci.yml).
    """

    def test_no_pii_leaks(self):
        examples = _load_examples()

        leak_total = 0
        leaks = []  # (индекс примера, тип) — БЕЗ самих значений ПДн
        types_leaked = set()

        for idx, ex in enumerate(examples):
            orig = ex["text"]
            anon = anonymize_text(orig)["anonymized"]
            for sp in ex["spans"]:
                value = orig[sp["start"] : sp["stop"]].strip()
                if not value:
                    continue
                leak_total += 1
                # утечка = оригинальное значение всё ещё присутствует в выводе
                if value in anon:
                    leaks.append((idx, sp["type"]))
                    types_leaked.add(sp["type"])

        assert leak_total > 0, "тест-сет пуст или без размеченных ПДн — проверить датасет"

        leak_rate = len(leaks) / leak_total * 100
        model_note = (
            "ruBERT активен" if person_model_available()
            else "ВНИМАНИЕ: модель PERSON НЕ загружена — распознавателя ФИО нет, "
                 "имена утекут. Проверьте PERSON_MODEL_DIR в .env"
        )
        # индексы примеров с утечкой (без значений ПДн) — для быстрой локализации
        example_idxs = sorted({i for i, _ in leaks})

        assert not leaks, (
            f"Утечка ПДн: {len(leaks)}/{leak_total} значений остались в тексте "
            f"(LeakRate {leak_rate:.2f}%). Типы: {sorted(types_leaked)}. "
            f"Примеры №: {example_idxs}. {model_note}. "
            f"Значения не выводятся намеренно (де-анонимизирующие данные)."
        )
