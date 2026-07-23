"""
Диагностика точности ПЛЕЙСХОЛДЕРОВ по типам ПДн (per-type).

Отвечает на вопрос «как модуль распознаёт date_of_birth, passport и т.д. —
под каким плейсхолдером реально прячет». В отличие от LeakRate (скрыли/нет,
без учёта типа) здесь ВАЖЕН тип: DATE_OF_BIRTH, спрятанный под <PII>, — это
промах по плейсхолдеру, хотя утечки нет.

Отличия от eval_2x2.py:
  - НЕТ алиаса DATE_TIME→DATE_OF_BIRTH: <PII>/DATE_TIME на дате рождения
    засчитывается как промах (честные цифры, а не завышенные);
  - строит матрицу ошибок: gold-тип → какой плейсхолдер фактически подставлен;
  - две картинки: per-type P/R/F2 и матрица плейсхолдеров.

Запуск (модель PERSON должна быть доступна через PERSON_MODEL_DIR/.env):
    python3 data/training/eval_per_type.py
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
OUT_DIR = os.environ.get(
    "CHARTS_DIR",
    "/home/egzod/Рабочий стол/report_anonymization/Графики метрик",
)
os.makedirs(OUT_DIR, exist_ok=True)

# Метка = плейсхолдер, который РЕАЛЬНО ложится в текст. Тип без своего оператора
# (например DATE_TIME) заменяется на <PII> (DEFAULT) — это и есть промах по
# плейсхолдеру, ради честности он НЕ переклеивается обратно на DATE_OF_BIRTH.
def placeholder_type(entity_type):
    if entity_type in OPERATORS:
        return entity_type
    return "PII"  # DEFAULT-оператор → <PII>


TYPES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "INN", "SNILS",
         "PASSPORT", "DATE_OF_BIRTH", "CREDIT_CARD"]
RU = {"PERSON": "Имена", "PHONE_NUMBER": "Телефоны", "EMAIL_ADDRESS": "Email",
      "INN": "ИНН", "SNILS": "СНИЛС", "PASSPORT": "Паспорт",
      "DATE_OF_BIRTH": "Дата рожд.", "CREDIT_CARD": "Карты"}

BLUE = "#4472C4"; GREEN = "#2E9E4F"; ORANGE = "#E08A00"; RED = "#C0392B"
GRAY = "#7F7F7F"; DARKBLUE = "#1F497D"


def overlap(a, b):
    return not (a[1] <= b[0] or b[1] <= a[0])


def ov_len(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def predict(text):
    """Возвращает спаны так, как они РЕАЛЬНО ложатся в текст: тот же
    непересекающийся набор (_resolve_overlaps по score), с меткой = фактический
    плейсхолдер. Именно это определяет и выходной текст, и mapping."""
    resolved = _resolve_overlaps(analyze_text(text))
    return [(placeholder_type(r.entity_type), r.start, r.end) for r in resolved]


def main():
    if not person_model_available():
        sys.exit("Модель PERSON недоступна — задайте PERSON_MODEL_DIR (см. .env).")

    examples = [json.loads(x) for x in open(TEST_PATH, encoding="utf-8")]

    relaxed = defaultdict(Counter)          # gold-тип -> tp/fp/fn (пересечение + точный тип)
    confusion = defaultdict(Counter)        # gold-тип -> предсказанный плейсхолдер (по max overlap)
    pred_types_seen = set()

    for ex in examples:
        orig = ex["text"]
        gold = [(sp["type"], sp["start"], sp["stop"]) for sp in ex["spans"]]
        pred = predict(orig)
        used = set()

        for gt, gs, ge in gold:
            # relaxed match: пересечение + СОВПАДЕНИЕ ТИПА (без алиаса даты)
            ri = next((i for i, (pt, ps, pe) in enumerate(pred)
                       if pt == gt and overlap((gs, ge), (ps, pe)) and i not in used), None)
            if ri is not None:
                relaxed[gt]["tp"] += 1
                used.add(ri)
            else:
                relaxed[gt]["fn"] += 1

            # матрица: какой плейсхолдер реально накрыл этот gold-спан (max overlap)
            best, best_len = None, 0
            for pt, ps, pe in pred:
                ol = ov_len((gs, ge), (ps, pe))
                if ol > best_len:
                    best, best_len = pt, ol
            label = best if best is not None else "—(пропуск)"
            confusion[gt][label] += 1
            pred_types_seen.add(label)

        # FP: предсказания, не легшие ни на один gold того же типа
        for i, (pt, _ps, _pe) in enumerate(pred):
            if i not in used:
                relaxed[pt]["fp"] += 1

    # ── per-type P/R/F2 ──
    rows = []
    for t in TYPES:
        c = relaxed[t]
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        p = tp / (tp + fp) * 100 if (tp + fp) else 100.0
        r = tp / (tp + fn) * 100 if (tp + fn) else 100.0
        f2 = (5 * p * r) / (4 * p + r) if (4 * p + r) else 0.0
        rows.append((t, tp, fp, fn, p, r, f2))
        print(f"{RU[t]:<12} TP={tp:<3} FP={fp:<3} FN={fn:<3}  P={p:5.1f}  R={r:5.1f}  F2={f2:5.1f}")

    # ════ ГРАФИК 1: per-type P/R/F2 ════
    fig, ax = plt.subplots(figsize=(13, 6.5))
    x = np.arange(len(TYPES)); w = 0.26
    P = [row[4] for row in rows]; R = [row[5] for row in rows]; F = [row[6] for row in rows]
    ax.bar(x - w, P, w, label="Precision (правильный тип)", color=BLUE, edgecolor="white")
    ax.bar(x,     R, w, label="Recall (нашли и типизировали)", color=GREEN, edgecolor="white")
    ax.bar(x + w, F, w, label="F2", color=ORANGE, edgecolor="white")
    for i in range(len(TYPES)):
        for off, val in [(-w, P[i]), (0, R[i]), (w, F[i])]:
            ax.text(i + off, val + 1.2, f"{val:.0f}", ha="center", fontsize=8, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([RU[t] for t in TYPES], rotation=15)
    ax.set_ylim(0, 115); ax.set_ylabel("%")
    ax.set_title("Точность ПЛЕЙСХОЛДЕРОВ по типам (relaxed, тип обязан совпасть)\n"
                 "Алиас DATE_TIME→DATE_OF_BIRTH снят: <PII> на дате рождения = промах",
                 fontsize=13, fontweight="bold", color=DARKBLUE, pad=14)
    ax.legend(fontsize=10, ncol=3, loc="lower center")
    ax.grid(axis="y", alpha=0.25); ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    p1 = os.path.join(OUT_DIR, "per_type_precision_recall_f2.png")
    plt.savefig(p1, dpi=150, bbox_inches="tight"); plt.close()

    # ════ ГРАФИК 2: матрица плейсхолдеров ════
    # колонки: сначала «правильные» типы, потом остальные наблюдённые + пропуск
    extra = [c for c in sorted(pred_types_seen) if c not in TYPES and c != "—(пропуск)"]
    cols = TYPES + extra + (["—(пропуск)"] if "—(пропуск)" in pred_types_seen else [])
    col_lbl = [RU.get(c, c) for c in cols]
    M = np.array([[confusion[g].get(c, 0) for c in cols] for g in TYPES], dtype=float)

    fig, ax = plt.subplots(figsize=(max(10, 1.1 * len(cols)), 6.5))
    im = ax.imshow(M, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(col_lbl, rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(len(TYPES))); ax.set_yticklabels([RU[t] for t in TYPES], fontsize=10)
    ax.set_xlabel("Какой плейсхолдер реально подставлен →", fontsize=10)
    ax.set_ylabel("Эталон (gold-тип)", fontsize=10)
    ax.set_title("Матрица плейсхолдеров: эталонный тип → фактически подставленный\n"
                 "Диагональ = верно; вне диагонали = не тот плейсхолдер; последний столбец = пропуск",
                 fontsize=12, fontweight="bold", color=DARKBLUE, pad=14)
    thr = M.max() / 2 if M.max() else 1
    for i in range(len(TYPES)):
        diag = cols[i] if i < len(cols) else None
        for j in range(len(cols)):
            v = int(M[i, j])
            if v == 0:
                continue
            wrong = cols[j] != TYPES[i]
            color = "white" if M[i, j] > thr else ("#B00000" if wrong else "#1F497D")
            ax.text(j, i, str(v), ha="center", va="center", fontsize=10,
                    fontweight="bold", color=color)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label="кол-во спанов")
    plt.tight_layout()
    p2 = os.path.join(OUT_DIR, "матрица_плейсхолдеров.png")
    plt.savefig(p2, dpi=150, bbox_inches="tight"); plt.close()

    print(f"\nГрафики сохранены:\n  {p1}\n  {p2}")


if __name__ == "__main__":
    main()
