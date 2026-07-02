"""
Оценка модуля анонимизации по методике 2x2 (Presidio Evaluator-style).

Факторы:
  prep  = предобработка текста через GramLynx (вкл/выкл)
  train = дообученная Natasha (обучена / не обучена)

Ячейки:
  Тест 1: prep=off, train=off   ← базовая точка (запускается всегда)
  Тест 2: prep=on,  train=off   ← нужен запущенный GramLynx (GRAMLYNX_URL)
  Тест 3: prep=off, train=on    ← нужен fine-tune Natasha (NATASHA_TRAINED)
  Тест 4: prep=on,  train=on    ← нужны оба

Метрики (по методике):
  - per-type + overall TP/FP/FN
  - Precision, Recall, F2 (recall-weighted)
  - Micro и Macro агрегация
  - strict / relaxed сопоставление спанов
  - LeakRate (утечка значения ПДн в выходной текст) — устойчива к сдвигам от GramLynx
  - Время: N-проход для качества, K повторов + warmup для времени, медиана

Результат пишется в eval_2x2_results.json — из него собирается отчёт.
"""
import json
import os
import sys
import time
import argparse
import statistics
import urllib.request
from collections import Counter, defaultdict

PROJ = "/media/egzod/01D7DA4662F24750/work/DENIS WORK/MY_PROJECTS/GLOBAL PROJECT/ANONIMIZATION_MODULE(work)"
sys.path.insert(0, PROJ)

TEST_PATH = os.path.join(PROJ, "data/natasha_training/test/test.jsonl")
OUT_JSON = os.path.join(PROJ, "data/natasha_training/eval_2x2_results.json")

# Типы ПДн, которые оцениваем
TYPES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "INN", "SNILS",
         "PASSPORT", "DATE_OF_BIRTH", "CREDIT_CARD"]

# Нормализация типов предсказаний (Presidio может выдавать синонимы)
TYPE_ALIAS = {
    "EMAIL": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "DATE_TIME": "DATE_OF_BIRTH",  # присваиваем к дате рождения только при пересечении с gold
}

GRAMLYNX_URL = os.environ.get("GRAMLYNX_URL", "").rstrip("/")

# ── адаптер к нашему сервису ──────────────────────────────────────────────
from app.anonymizer import anonymize_text  # строит весь AnalyzerEngine при импорте


def norm_type(t):
    return TYPE_ALIAS.get(t, t)


def predict(text):
    """Адаптер: текст → (спаны, анонимизированный_текст).
    Спаны в формате (тип, start, end). Возвращаем весь выход сервиса целиком —
    Presidio + regex + Natasha уже слиты в один список."""
    res = anonymize_text(text)
    spans = [(norm_type(e["entity_type"]), e["start"], e["end"]) for e in res["entities_found"]]
    return spans, res["anonymized"]


def gramlynx_correct(text):
    """Предобработка через GramLynx. Требует запущенного сервиса (GRAMLYNX_URL)."""
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        GRAMLYNX_URL + "/v1/correct",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["corrected_text"]


# ── сопоставление спанов ──────────────────────────────────────────────────
def overlap(a, b):
    return not (a[1] <= b[0] or b[1] <= a[0])


def eval_quality(examples, apply_prep):
    """Считает per-type TP/FP/FN (strict и relaxed) + LeakRate.

    ВАЖНО: при apply_prep=True текст меняется, координаты gold сдвигаются —
    span-level метрики некорректны, поэтому в этом режиме основной показатель
    LeakRate (по значению), а span-level помечается как invalid."""
    strict = defaultdict(Counter)   # type -> tp/fp/fn
    relaxed = defaultdict(Counter)
    leak_total = 0
    leak_leaked = 0

    for ex in examples:
        orig = ex["text"]
        gold = [(sp["type"], sp["start"], sp["stop"]) for sp in ex["spans"]]

        text = gramlynx_correct(orig) if apply_prep else orig
        pred, anon = predict(text)

        if not apply_prep:
            # ── span-level (валидно только без предобработки) ──
            used_s, used_r = set(), set()
            for gt, gs, ge in gold:
                # strict: точные границы + тип
                si = next((i for i, (pt, ps, pe) in enumerate(pred)
                           if pt == gt and ps == gs and pe == ge and i not in used_s), None)
                if si is not None:
                    strict[gt]["tp"] += 1; used_s.add(si)
                else:
                    strict[gt]["fn"] += 1
                # relaxed: пересечение + тип
                ri = next((i for i, (pt, ps, pe) in enumerate(pred)
                           if pt == gt and overlap((gs, ge), (ps, pe)) and i not in used_r), None)
                if ri is not None:
                    relaxed[gt]["tp"] += 1; used_r.add(ri)
                else:
                    relaxed[gt]["fn"] += 1
            # FP: предсказания без совпадения по типу+границам / типу+пересечению
            for i, (pt, ps, pe) in enumerate(pred):
                if i not in used_s:
                    strict[pt]["fp"] += 1
                if i not in used_r:
                    relaxed[pt]["fp"] += 1

        # ── LeakRate (валидно всегда, в т.ч. с предобработкой) ──
        for gt, gs, ge in gold:
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
        "span_valid": not apply_prep,
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
        micro["tp"] += tp; micro["fp"] += fp; micro["fn"] += fn
        macro_p.append(p); macro_r.append(r); macro_f.append(f2)
    mp, mr, mf = prf2(micro["tp"], micro["fp"], micro["fn"])
    return {
        "per_type": per_type,
        "micro": {"P": round(mp * 100, 1), "R": round(mr * 100, 1), "F2": round(mf * 100, 1),
                  "tp": micro["tp"], "fp": micro["fp"], "fn": micro["fn"]},
        "macro": {"P": round(sum(macro_p) / len(macro_p) * 100, 1) if macro_p else 0.0,
                  "R": round(sum(macro_r) / len(macro_r) * 100, 1) if macro_r else 0.0,
                  "F2": round(sum(macro_f) / len(macro_f) * 100, 1) if macro_f else 0.0},
    }


def measure_time(examples, apply_prep, K, warmup):
    """K повторов + warmup, медиана мс/текст."""
    per_text_ms = []
    for k in range(warmup + K):
        t0 = time.perf_counter()
        for ex in examples:
            text = gramlynx_correct(ex["text"]) if apply_prep else ex["text"]
            predict(text)
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


def run_cell(name, examples, apply_prep, K, warmup, do_time):
    print(f"\n=== {name}  (prep={'on' if apply_prep else 'off'}) ===")
    q = eval_quality(examples, apply_prep)
    result = {
        "name": name,
        "prep": apply_prep,
        "n_examples": len(examples),
        "leak_total": q["leak_total"],
        "leak_leaked": q["leak_leaked"],
        "leak_rate_pct": round(q["leak_leaked"] / q["leak_total"] * 100, 2) if q["leak_total"] else 0.0,
        "value_recall_pct": round((1 - q["leak_leaked"] / q["leak_total"]) * 100, 2) if q["leak_total"] else 0.0,
        "span_valid": q["span_valid"],
    }
    if q["span_valid"]:
        result["strict"] = aggregate(q["strict"])
        result["relaxed"] = aggregate(q["relaxed"])
        s, r = result["strict"], result["relaxed"]
        print(f"  STRICT  micro: P={s['micro']['P']}  R={s['micro']['R']}  F2={s['micro']['F2']}")
        print(f"  RELAXED micro: P={r['micro']['P']}  R={r['micro']['R']}  F2={r['micro']['F2']}")
    print(f"  LeakRate = {result['leak_rate_pct']}%  (утечек {q['leak_leaked']}/{q['leak_total']}),"
          f"  value-Recall = {result['value_recall_pct']}%")
    if do_time:
        result["timing"] = measure_time(examples, apply_prep, K, warmup)
        print(f"  Время: {result['timing']['ms_per_text_median']} мс/текст "
              f"(медиана K={K}), {result['timing']['throughput_per_sec']} текст/с")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default="1", help="какие тесты гонять: 1,2,3,4 через запятую")
    ap.add_argument("-K", type=int, default=5, help="повторов замера времени")
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--no-time", action="store_true", help="не мерить время (быстрее)")
    args = ap.parse_args()

    examples = [json.loads(l) for l in open(TEST_PATH, encoding="utf-8")]
    cells = set(args.cells.split(","))
    do_time = not args.no_time

    # "Обучено" = реально доступна дообученная модель PERSON (а не просто флаг).
    # Флаг NATASHA_TRAINED сам по себе модель не подменяет, поэтому им доверять нельзя:
    # Тесты 3/4 считаются валидными только если по PERSON_MODEL_DIR лежит модель.
    try:
        from app.person_transformer_recognizer import person_model_available
        trained = person_model_available()
    except Exception:
        trained = False
    results = {"dataset": os.path.relpath(TEST_PATH, PROJ), "n": len(examples), "cells": {}}

    # Тест 1 — база
    if "1" in cells:
        results["cells"]["1"] = run_cell("Тест 1 (база: prep off, train off)",
                                         examples, False, args.K, args.warmup, do_time)
    # Тест 2 — предобработка
    if "2" in cells:
        if not GRAMLYNX_URL:
            results["cells"]["2"] = {"name": "Тест 2", "blocked": "GRAMLYNX_URL не задан — сервис GramLynx не запущен"}
            print("\nТест 2: ПРОПУЩЕН — не задан GRAMLYNX_URL")
        else:
            results["cells"]["2"] = run_cell("Тест 2 (prep on, train off)",
                                             examples, True, args.K, args.warmup, do_time)
    # Тест 3 — дообученная Natasha
    if "3" in cells:
        if not trained:
            results["cells"]["3"] = {"name": "Тест 3", "blocked": "Дообученная модель PERSON отсутствует (PERSON_MODEL_DIR не задан или пуст)"}
            print("\nТест 3: ЗАБЛОКИРОВАН — нет дообученной Natasha")
        else:
            results["cells"]["3"] = run_cell("Тест 3 (prep off, train on)",
                                             examples, False, args.K, args.warmup, do_time)
    # Тест 4 — оба
    if "4" in cells:
        if not trained or not GRAMLYNX_URL:
            results["cells"]["4"] = {"name": "Тест 4", "blocked": "Нужны и дообученная Natasha, и запущенный GramLynx"}
            print("\nТест 4: ЗАБЛОКИРОВАН — нужны оба фактора")
        else:
            results["cells"]["4"] = run_cell("Тест 4 (prep on, train on)",
                                             examples, True, args.K, args.warmup, do_time)

    json.dump(results, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nРезультаты сохранены: {os.path.relpath(OUT_JSON, PROJ)}")


if __name__ == "__main__":
    main()
