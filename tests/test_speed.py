"""
Скорость обработки: латентность и пропускная способность.

Ось 4 (цель): нагрузочное/производительность.
Ось 1 (доступ): чёрный ящик — дёргаем публичную функцию, внутрь не смотрим.
Ось 3 (уровень): системное — меряем всю цепочку на один текст.

Смысл простыми словами: замеряем, сколько миллисекунд уходит на один текст.
Первые прогоны выбрасываем (прогрев модели), из остальных берём медиану —
она устойчива к случайным выбросам, в отличие от среднего.

Зачем нужен: ловит катастрофические просадки. Реальный пример из практики —
предобработку GramLynx отклонили именно потому, что она замедляла обработку
в 4-5 раз при нулевом выигрыше по приватности.

Бюджет намеренно щедрый: фактическая медиана ~10 мс/текст с моделью и ~6 мс без
неё (CPU). Порог в 150 мс не ловит мелкие колебания и не шумит на медленных
CI-раннерах, но поймает регресс на порядок.
"""

import statistics
import time

import pytest

from app.anonymizer import anonymize_text

# Порог: медиана мс на один текст. См. обоснование в докстринге модуля.
LATENCY_BUDGET_MS = 150.0

WARMUP_RUNS = 2
MEASURE_RUNS = 5

SAMPLE_TEXTS = [
    "Иван Петров, телефон +79991234567",
    "ИНН 7701234560, почта client@mail.ru",
    "СНИЛС 112-233-445 95, паспорт 4509 123456",
    "Карта 4276 3800 1234 5678, дата рождения 12.03.1990",
    "Сегодня хорошая погода, персональных данных здесь нет",
]


def _median_ms_per_text() -> float:
    for _ in range(WARMUP_RUNS):
        for t in SAMPLE_TEXTS:
            anonymize_text(t)

    per_run = []
    for _ in range(MEASURE_RUNS):
        started = time.perf_counter()
        for t in SAMPLE_TEXTS:
            anonymize_text(t)
        per_run.append((time.perf_counter() - started) / len(SAMPLE_TEXTS) * 1000)
    return statistics.median(per_run)


@pytest.mark.speed
class TestLatency:
    """Латентность обработки одного текста."""

    def test_median_latency_within_budget(self):
        median_ms = _median_ms_per_text()
        throughput = 1000.0 / median_ms

        # Печатаем всегда (pytest -s) — цифра полезна как тренд, а не только
        # как факт прохождения.
        print(
            f"\n  латентность: {median_ms:.1f} мс/текст (медиана из {MEASURE_RUNS} "
            f"прогонов, прогрев {WARMUP_RUNS})"
            f"\n  пропускная способность: {throughput:.0f} текстов/с"
            f"\n  бюджет: {LATENCY_BUDGET_MS:.0f} мс/текст"
        )

        assert median_ms < LATENCY_BUDGET_MS, (
            f"обработка замедлилась: {median_ms:.1f} мс/текст при бюджете "
            f"{LATENCY_BUDGET_MS:.0f} мс. Это регресс производительности на порядок — "
            f"проверьте, не добавился ли тяжёлый шаг в пайплайн."
        )

    def test_empty_text_is_fast(self):
        """Пустой вход не должен запускать пайплайн вообще."""
        started = time.perf_counter()
        for _ in range(100):
            anonymize_text("")
        elapsed_ms = (time.perf_counter() - started) / 100 * 1000

        assert elapsed_ms < 1.0, (
            f"пустой текст обрабатывается {elapsed_ms:.3f} мс — должен отсекаться "
            f"сразу, без запуска анализатора"
        )
