#!/usr/bin/env python3
"""
Демо обезличивания: показывает вход → выход на примерах из held-out тест-сета.

Зачем: тесты проверяют результат утверждениями и ничего не печатают (pytest
перехватывает stdout) — глазами работу модуля через них не увидеть. Здесь
берутся реальные примеры тест-сета (синтетика) и печатается, что пришло и что
получилось, плюс какие типы ПДн найдены.

Использование:
    ./scripts/demo_examples.py          # 3 примера
    ./scripts/demo_examples.py -n 10    # больше примеров
    ./scripts/demo_examples.py --random # случайные, а не первые разнообразные

БЕЗОПАСНОСТЬ: mapping (ключ де-анонимизации) намеренно НЕ печатается.
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_PATH = os.path.join(ROOT, "data", "training", "test", "test.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description="Демо: вход → выход обезличивания")
    ap.add_argument("-n", type=int, default=3, help="сколько примеров показать")
    ap.add_argument("--random", action="store_true",
                    help="случайные примеры вместо первых разнообразных")
    args = ap.parse_args()

    from app.person_transformer_recognizer import person_model_available
    if not person_model_available():
        print("  ⚠ Модель PERSON не найдена (PERSON_MODEL_DIR) — ФИО в демо "
              "распознаваться не будут.")

    from app.anonymizer import _resolve_overlaps, analyze_text, anonymize_text

    examples = [json.loads(x) for x in open(TEST_PATH, encoding="utf-8")]
    if args.random:
        picked = random.sample(examples, min(args.n, len(examples)))
    else:
        # первые N, стараясь не повторять состав типов ПДн — чтобы показать разное
        picked, seen = [], set()
        for ex in examples:
            types = frozenset(s["type"] for s in ex["spans"])
            if types not in seen or len(picked) < args.n // 2:
                picked.append(ex)
                seen.add(types)
            if len(picked) >= args.n:
                break

    for i, ex in enumerate(picked, 1):
        res = anonymize_text(ex["text"])
        # показываем резолвнутый набор (без пересекающихся дублей) — ровно те
        # типы, чьи плейсхолдеры реально стоят в выходном тексте
        found = sorted({r.entity_type for r in _resolve_overlaps(analyze_text(ex["text"]))})
        print(f"─── Пример {i} ───")
        print(f"  ВХОД:    {ex['text']}")
        print(f"  ВЫХОД:   {res['anonymized']}")
        print(f"  найдено: {', '.join(found) if found else '(ПДн не найдено)'}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
