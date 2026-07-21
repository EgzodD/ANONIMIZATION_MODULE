"""
Оценка качества обезличивания на held-out наборе (Presidio Evaluator-style).

Что меряет: насколько полно и точно модуль находит ПДн в тексте. Оценивается
ОДНА конфигурация — та модель PERSON, что сейчас загружена (определяется
переменной PERSON_MODEL_DIR). Чтобы сравнить две модели (например базовую и
нашу дообученную), скрипт запускают дважды с разным PERSON_MODEL_DIR и сводят
результаты.

История: раньше здесь был факторный план 2×2 (предобработка GramLynx × модель).
Предобработка отклонена по результатам замеров (×4-5 латентности при нулевом
выигрыше по приватности) и удалена из проекта — вместе с ней убран весь prep-код
и выравнивание координат. Осталась одна ось — модель. Имя файла (eval_2x2)
сохранено историческим, чтобы не рвать ссылки; по сути это уже оценка одной
конфигурации.

Метрики:
  - per-type + overall TP/FP/FN
  - Precision, Recall, F2 (recall-weighted)
  - Micro и Macro агрегация
  - strict / relaxed сопоставление спанов
  - LeakRate (значение ПДн осталось в выходном тексте) — главный показатель приватности
  - Время: K повторов + warmup, медиана мс/текст

Результат пишется в JSON (по умолчанию eval_2x2_results.json) — из него собирается отчёт.
"""
import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict

PROJ = "/media/egzod/01D7DA4662F24750/work/DENIS WORK/MY_PROJECTS/GLOBAL PROJECT/ANONIMIZATION_MODULE(work)"
sys.path.insert(0, PROJ)

TEST_PATH = os.path.join(PROJ, "data/natasha_training/test/test.jsonl")
DEFAULT_OUT = os.path.join(PROJ, "data/natasha_training/eval_2x2_results.json")

# Типы ПДн, которые оцениваем
TYPES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "INN", "SNILS",
         "PASSPORT", "DATE_OF_BIRTH", "CREDIT_CARD"]

# Нормализация типов предсказаний (Presidio может выдавать синонимы)
TYPE_ALIAS = {
    "EMAIL": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "DATE_TIME": "DATE_OF_BIRTH",  # присваиваем к дате рождения только при пересечении с gold
}

# ── адаптер к нашему сервису ──────────────────────────────────────────────
# noqa: E402 — импорт после sys.path.insert(PROJ), иначе app не найдётся
from app.anonymizer import anonymize_text  # noqa: E402  (строит AnalyzerEngine при импорте)


def norm_type(t):
    return TYPE_ALIAS.get(t, t)


def predict(text):
    """Адаптер: текст → (спаны, анонимизированный_текст).
    Спаны в формате (тип, start, end). Возвращаем весь выход сервиса целиком —
    Presidio + regex + модель PERSON уже слиты в один список."""
    res = anonymize_text(text)
    spans = [(norm_type(e["entity_type"]), e["start"], e["end"]) for e in res["entities_found"]]
    return spans, res["anonymized"]


# ── сопоставление спанов ──────────────────────────────────────────────────
def overlap(a, b):
    return not (a[1] <= b[0] or b[1] <= a[0])


def eval_quality(examples):
    """Считает per-type TP/FP/FN (strict и relaxed) + LeakRate.

    Разметка (gold) сделана по оригинальному тексту; модуль его не переписывает,
    поэтому координаты совпадают напрямую и никакого выравнивания не нужно."""
    strict = defaultdict(Counter)   # type -> tp/fp/fn
    relaxed = defaultdict(Counter)
    leak_total = 0
    leak_leaked = 0

    for ex in examples:
        orig = ex["text"]
        gold = [(sp["type"], sp["start"], sp["stop"]) for sp in ex["spans"]]
        pred, anon = predict(orig)

        # ── span-level ──
        used_s, used_r = set(), set()
        for gt, gs, ge in gold:
            # strict: точные границы + тип
            si = next((i for i, (pt, ps, pe) in enumerate(pred)
                       if pt == gt and ps == gs and pe == ge and i not in used_s), None)
            if si is not None:
                strict[gt]["tp"] += 1
                used_s.add(si)
            else:
                strict[gt]["fn"] += 1
            # relaxed: пересечение + тип
            ri = next((i for i, (pt, ps, pe) in enumerate(pred)
                       if pt == gt and overlap((gs, ge), (ps, pe)) and i not in used_r), None)
            if ri is not None:
                relaxed[gt]["tp"] += 1
                used_r.add(ri)
            else:
                relaxed[gt]["fn"] += 1
        # FP: предсказания без совпадения по типу+границам / типу+пересечению
        for i, (pt, _ps, _pe) in enumerate(pred):
            if i not in used_s:
                strict[pt]["fp"] += 1
            if i not in used_r:
                relaxed[pt]["fp"] += 1

        # ── LeakRate (по значению ПДн) ──
        for _gt, gs, ge in gold:
            value = orig[gs:ge].strip()
            if not value:
                continue
            leak_total += 1
            # утечка = значение всё ещё присутствует в анонимизированном тексте
            if value in anon:
                leak_leaked += 1

    return {
        "strict": {t: dict(strict[t]) for t in strict},
        "relaxed": {t: dict(relaxed[t]) for t in relaxed},
        "leak_total": leak_total,
        "leak_leaked": leak_leaked,
    }


def prf2(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    f2 = (5 * p * r) / (4 * p + r) if (4 * p + r) else 0.0
    return p, r, f2


def aggregate(counts_by_type):
    """Возвращает per-type P/R/F2 + micro + macro."""
    per_type = {}
    micro = Counter()
    macro_p, macro_r, macro_f = [], [], []
    for t in TYPES:
        c = counts_by_type.get(t, {})
        tp, fp, fn = c.get("tp", 0), c.get("fp", 0), c.get("fn", 0)
        if tp + fp + fn == 0:
            continue
        p, r, f2 = prf2(tp, fp, fn)
        per_type[t] = {"tp": tp, "fp": fp, "fn": fn,
                       "P": round(p * 100, 1), "R": round(r * 100, 1), "F2": round(f2 * 100, 1)}
        micro["tp"] += tp
        micro["fp"] += fp
        micro["fn"] += fn
        macro_p.append(p)
        macro_r.append(r)
        macro_f.append(f2)
    mp, mr, mf = prf2(micro["tp"], micro["fp"], micro["fn"])
    return {
        "per_type": per_type,
        "micro": {"P": round(mp * 100, 1), "R": round(mr * 100, 1), "F2": round(mf * 100, 1),
                  "tp": micro["tp"], "fp": micro["fp"], "fn": micro["fn"]},
        "macro": {"P": round(sum(macro_p) / len(macro_p) * 100, 1) if macro_p else 0.0,
                  "R": round(sum(macro_r) / len(macro_r) * 100, 1) if macro_r else 0.0,
                  "F2": round(sum(macro_f) / len(macro_f) * 100, 1) if macro_f else 0.0},
    }


def measure_time(examples, K, warmup):
    """K повторов + warmup, медиана мс/текст."""
    per_text_ms = []
    for k in range(warmup + K):
        t0 = time.perf_counter()
        for ex in examples:
            predict(ex["text"])
        dt = (time.perf_counter() - t0) / len(examples) * 1000.0
        if k >= warmup:
            per_text_ms.append(dt)
    return {
        "ms_per_text_median": round(statistics.median(per_text_ms), 2),
        "ms_per_text_mean": round(statistics.mean(per_text_ms), 2),
        "ms_per_text_std": round(statistics.pstdev(per_text_ms), 2) if len(per_text_ms) > 1 else 0.0,
        "throughput_per_sec": round(1000.0 / statistics.median(per_text_ms), 1),
        "repeats_K": K, "warmup": warmup,
    }


def run_eval(label, examples, K, warmup, do_time):
    print(f"\n=== {label} ===")
    q = eval_quality(examples)
    result = {
        "label": label,
        "n_examples": len(examples),
        "leak_total": q["leak_total"],
        "leak_leaked": q["leak_leaked"],
        "leak_rate_pct": round(q["leak_leaked"] / q["leak_total"] * 100, 2) if q["leak_total"] else 0.0,
        "value_recall_pct": round((1 - q["leak_leaked"] / q["leak_total"]) * 100, 2) if q["leak_total"] else 0.0,
        "strict": aggregate(q["strict"]),
        "relaxed": aggregate(q["relaxed"]),
    }
    s, r = result["strict"], result["relaxed"]
    print(f"  STRICT  micro: P={s['micro']['P']}  R={s['micro']['R']}  F2={s['micro']['F2']}")
    print(f"  RELAXED micro: P={r['micro']['P']}  R={r['micro']['R']}  F2={r['micro']['F2']}")
    print(f"  LeakRate = {result['leak_rate_pct']}%  (утечек {q['leak_leaked']}/{q['leak_total']}),"
          f"  value-Recall = {result['value_recall_pct']}%")
    if do_time:
        result["timing"] = measure_time(examples, K, warmup)
        print(f"  Время: {result['timing']['ms_per_text_median']} мс/текст "
              f"(медиана K={K}), {result['timing']['throughput_per_sec']} текст/с")
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Оценка качества обезличивания текущей модели PERSON на held-out наборе."
    )
    ap.add_argument("--label", default=None,
                    help="как назвать конфигурацию в результате (по умолчанию — по наличию модели)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="куда писать JSON с результатами")
    ap.add_argument("-K", type=int, default=5, help="повторов замера времени")
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--no-time", action="store_true", help="не мерить время (быстрее)")
    args = ap.parse_args()

    examples = [json.loads(line) for line in open(TEST_PATH, encoding="utf-8")]
    do_time = not args.no_time

    # Какая модель фактически загружена — по ней и подписываем прогон.
    try:
        from app.person_transformer_recognizer import person_model_available
        trained = person_model_available()
    except Exception:
        trained = False
    label = args.label or ("дообученная модель PERSON" if trained
                           else "без модели PERSON (ФИО не распознаются)")

    result = run_eval(label, examples, args.K, args.warmup, do_time)

    out = {
        "dataset": os.path.relpath(TEST_PATH, PROJ),
        "n": len(examples),
        "model_loaded": trained,
        "result": result,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nРезультаты сохранены: {os.path.relpath(args.out, PROJ)}")


if __name__ == "__main__":
    main()
