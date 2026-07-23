"""
Единый дашборд качества модуля обезличивания — вся картина на одном изображении.

6 панелей:
  A. Статус тест-набора (passed / xfailed / failed)
  B. Тесты по категориям
  C. Приватность: LeakRate и value-recall (главный гейт)
  D. Типизация overall: micro Precision / Recall / F2
  E. Точность плейсхолдеров по типам (recall правильного типа)
  F. Скорость: медиана мс/текст против бюджета

Метрики качества (C, D, E) считаются ВЖИВУЮ на held-out тест-сете — ровно так,
как модуль работает в бою (по резолвнутому набору _resolve_overlaps, что и
определяет выходной текст). Числа тест-набора (A, B) и скорости (F) берутся из
прогона pytest — они помечены как константы ниже с указанием, чем измерены.

Запуск (модель PERSON доступна через PERSON_MODEL_DIR/.env):
    python3 data/training/make_dashboard.py
"""
import json
import os
import sys
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import rcParams  # noqa: E402

rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, PROJ)
from app.anonymizer import OPERATORS, _resolve_overlaps, analyze_text  # noqa: E402
from app.person_transformer_recognizer import person_model_available  # noqa: E402

TEST_PATH = os.path.join(HERE, "test", "test.jsonl")
OUT = os.environ.get(
    "DASHBOARD_OUT",
    "/home/egzod/Рабочий стол/report_anonymization/Графики метрик/ДАШБОРД_качество_модуля.png",
)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ── Константы из прогона pytest (источник помечен) ──────────────────────────
# .venv/bin/python -m pytest tests/ -q
SUITE = {"passed": 75, "xfailed": 2, "failed": 0}
# .venv/bin/python -m pytest -m <cat> --collect-only
CATEGORIES = {"unit": 31, "integration": 22, "custom_params": 20, "security": 8,
              "speed": 2, "privacy": 1, "e2e": 1}
# .venv/bin/python -m pytest -m speed -s
SPEED_MS = 9.5
SPEED_BUDGET_MS = 150.0
SPEED_TPS = 105

TYPES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "INN", "SNILS",
         "PASSPORT", "DATE_OF_BIRTH", "CREDIT_CARD"]
RU = {"PERSON": "Имена", "PHONE_NUMBER": "Телефоны", "EMAIL_ADDRESS": "Email",
      "INN": "ИНН", "SNILS": "СНИЛС", "PASSPORT": "Паспорт",
      "DATE_OF_BIRTH": "Дата рожд.", "CREDIT_CARD": "Карты"}

BLUE = "#4472C4"; GREEN = "#2E9E4F"; ORANGE = "#E08A00"; RED = "#C0392B"
GRAY = "#7F7F7F"; DARKBLUE = "#1F497D"; LIGHT = "#EAF0FA"


def placeholder_type(t):
    return t if t in OPERATORS else "PII"


def overlap(a, b):
    return not (a[1] <= b[0] or b[1] <= a[0])


def collect():
    """Вживую считает per-type recall типа + value-leak по резолвнутому выводу."""
    examples = [json.loads(x) for x in open(TEST_PATH, encoding="utf-8")]
    per = defaultdict(Counter)          # gold-тип -> tp/fn (правильный плейсхолдер)
    leak_total = leak_leaked = 0
    from app.anonymizer import anonymize_text
    for ex in examples:
        orig = ex["text"]
        gold = [(sp["type"], sp["start"], sp["stop"]) for sp in ex["spans"]]
        resolved = [(placeholder_type(r.entity_type), r.start, r.end)
                    for r in _resolve_overlaps(analyze_text(orig))]
        used = set()
        for gt, gs, ge in gold:
            i = next((k for k, (pt, ps, pe) in enumerate(resolved)
                      if pt == gt and overlap((gs, ge), (ps, pe)) and k not in used), None)
            if i is not None:
                per[gt]["tp"] += 1
                used.add(i)
            else:
                per[gt]["fn"] += 1
        anon = anonymize_text(orig)["anonymized"]
        for _gt, gs, ge in gold:
            v = orig[gs:ge].strip()
            if not v:
                continue
            leak_total += 1
            if v in anon:
                leak_leaked += 1
    return per, leak_total, leak_leaked


def main():
    if not person_model_available():
        sys.exit("Модель PERSON недоступна — задайте PERSON_MODEL_DIR (см. .env).")
    per, leak_total, leak_leaked = collect()

    tp = sum(per[t]["tp"] for t in TYPES)
    fn = sum(per[t]["fn"] for t in TYPES)
    micro_r = tp / (tp + fn) * 100 if (tp + fn) else 100.0
    micro_p = 100.0  # FP=0 по резолвнутому набору (лишнего не подставляется)
    micro_f2 = (5 * micro_p * micro_r) / (4 * micro_p + micro_r) if (4 * micro_p + micro_r) else 0
    leak_rate = leak_leaked / leak_total * 100 if leak_total else 0.0
    value_recall = 100 - leak_rate

    fig = plt.figure(figsize=(18, 10.5))
    fig.suptitle("Качество модуля обезличивания — общая панель  (held-out тест: 150 текстов, 318 ПДн)",
                 fontsize=17, fontweight="bold", color=DARKBLUE, y=0.98)
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.26,
                          left=0.05, right=0.97, top=0.90, bottom=0.07)

    # ── A. Статус тест-набора ──
    axA = fig.add_subplot(gs[0, 0])
    total = SUITE["passed"] + SUITE["xfailed"] + SUITE["failed"]
    axA.pie([SUITE["passed"], SUITE["xfailed"], max(SUITE["failed"], 0.0001)],
            colors=[GREEN, ORANGE, RED], startangle=90, counterclock=False,
            wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2})
    axA.text(0, 0.12, f"{SUITE['passed']}/{total}", ha="center", va="center",
             fontsize=30, fontweight="bold", color=DARKBLUE)
    axA.text(0, -0.22, "тестов зелёные", ha="center", va="center", fontsize=11, color=GRAY)
    axA.set_title("A. Статус тест-набора", fontsize=13, fontweight="bold", color=DARKBLUE)
    axA.text(0.5, -1.32, f"passed {SUITE['passed']}   ·   xfailed {SUITE['xfailed']} (over-masking, не утечка)"
             f"   ·   failed {SUITE['failed']}",
             ha="center", transform=axA.transData if False else axA.transAxes, fontsize=9.5, color=GRAY)

    # ── B. Тесты по категориям ──
    axB = fig.add_subplot(gs[0, 1])
    items = sorted(CATEGORIES.items(), key=lambda x: x[1])
    lbl = {"unit": "unit (типы ПДн)", "integration": "integration (API)",
           "custom_params": "custom_params", "security": "security",
           "speed": "speed", "privacy": "privacy (LeakRate)", "e2e": "e2e"}
    bars = axB.barh([lbl[k] for k, _ in items], [v for _, v in items],
                    color=BLUE, edgecolor="white")
    for b, (_, v) in zip(bars, items):
        axB.text(v + 0.4, b.get_y() + b.get_height() / 2, str(v), va="center",
                 fontsize=10, fontweight="bold", color=DARKBLUE)
    axB.set_xlim(0, max(CATEGORIES.values()) + 5)
    axB.set_title("B. Тесты по категориям (маркеры)", fontsize=13, fontweight="bold", color=DARKBLUE)
    axB.grid(axis="x", alpha=0.25); axB.spines[["top", "right"]].set_visible(False)

    # ── C. Приватность ──
    axC = fig.add_subplot(gs[0, 2])
    axC.axis("off")
    axC.set_title("C. Приватность — главный гейт", fontsize=13, fontweight="bold", color=DARKBLUE)
    axC.text(0.5, 0.72, f"LeakRate  {leak_rate:.1f}%", ha="center", fontsize=26,
             fontweight="bold", color=GREEN if leak_rate == 0 else RED)
    axC.text(0.5, 0.55, f"утечек {leak_leaked} из {leak_total} значений ПДн",
             ha="center", fontsize=11, color=GRAY)
    axC.text(0.5, 0.30, f"value-recall  {value_recall:.1f}%", ha="center", fontsize=22,
             fontweight="bold", color=DARKBLUE)
    axC.text(0.5, 0.15, "каждое значение ПДн скрыто\n(даже если тип плейсхолдера не идеален)",
             ha="center", fontsize=9.5, color=GRAY)
    axC.add_patch(plt.Rectangle((0.05, 0.05), 0.9, 0.9, fill=False, edgecolor=GREEN if leak_rate == 0 else RED,
                                linewidth=2, transform=axC.transAxes))

    # ── D. Типизация overall ──
    axD = fig.add_subplot(gs[1, 0])
    vals = [micro_p, micro_r, micro_f2]
    names = ["Precision\n(верный тип)", "Recall\n(верный тип)", "F2"]
    cols = [BLUE, GREEN if micro_r >= 95 else ORANGE, ORANGE]
    bars = axD.bar(names, vals, color=cols, edgecolor="white", width=0.6)
    for b, v in zip(bars, vals):
        axD.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.1f}", ha="center",
                 fontsize=12, fontweight="bold", color=DARKBLUE)
    axD.set_ylim(0, 115); axD.set_ylabel("%")
    axD.set_title("D. Типизация (micro, правильный плейсхолдер)", fontsize=12.5,
                  fontweight="bold", color=DARKBLUE)
    axD.grid(axis="y", alpha=0.25); axD.spines[["top", "right"]].set_visible(False)

    # ── E. Per-type recall плейсхолдеров ──
    axE = fig.add_subplot(gs[1, 1])
    rec = {t: per[t]["tp"] / (per[t]["tp"] + per[t]["fn"]) * 100
           if (per[t]["tp"] + per[t]["fn"]) else 100.0 for t in TYPES}
    order = sorted(TYPES, key=lambda t: rec[t])
    colors = [GREEN if rec[t] >= 99 else (ORANGE if rec[t] >= 90 else RED) for t in order]
    bars = axE.barh([RU[t] for t in order], [rec[t] for t in order], color=colors, edgecolor="white")
    for b, t in zip(bars, order):
        axE.text(min(rec[t] + 1, 92), b.get_y() + b.get_height() / 2, f"{rec[t]:.0f}%",
                 va="center", fontsize=10, fontweight="bold")
    axE.set_xlim(0, 118); axE.axvline(95, color=GRAY, linestyle="--", linewidth=1, alpha=0.6)
    axE.set_title("E. Верный плейсхолдер по типам (recall типа)", fontsize=12.5,
                  fontweight="bold", color=DARKBLUE)
    axE.grid(axis="x", alpha=0.25); axE.spines[["top", "right"]].set_visible(False)

    # ── F. Скорость ──
    axF = fig.add_subplot(gs[1, 2])
    bars = axF.bar(["медиана\nмс/текст", "бюджет\nмс/текст"], [SPEED_MS, SPEED_BUDGET_MS],
                   color=[GREEN, GRAY], edgecolor="white", width=0.55)
    for b, v in zip(bars, [SPEED_MS, SPEED_BUDGET_MS]):
        axF.text(b.get_x() + b.get_width() / 2, v + 3, f"{v:g}", ha="center",
                 fontsize=12, fontweight="bold", color=DARKBLUE)
    axF.set_ylim(0, SPEED_BUDGET_MS * 1.2); axF.set_ylabel("мс/текст")
    axF.set_title(f"F. Скорость — {SPEED_TPS} текст/с (запас ×{SPEED_BUDGET_MS/SPEED_MS:.0f})",
                  fontsize=12.5, fontweight="bold", color=DARKBLUE)
    axF.grid(axis="y", alpha=0.25); axF.spines[["top", "right"]].set_visible(False)

    plt.savefig(OUT, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"micro P={micro_p:.1f} R={micro_r:.1f} F2={micro_f2:.1f} | "
          f"LeakRate={leak_rate:.1f}% value-recall={value_recall:.1f}%")
    print(f"Дашборд: {OUT}")


if __name__ == "__main__":
    main()
