"""
Дистилляция модели PERSON в rubert-tiny2 (Track B). Запускать в Colab (GPU).

Схема (см. DISTILLATION_RECIPE.md):
  gold  = train.conll + train_negatives.conll   (наши метки, вес 1.0)
  silver= corpus.conll                          (метки учителя, вес SILVER_WEIGHT)
  ученик= cointegrated/rubert-tiny2, обучается на gold+silver со взвешенным loss.
Приоритет — recall (пропуск ФИО = утечка), поэтому лучшая модель по F2.

Перед запуском получить silver-метки учителем: см. label_silver_with_teacher()
внизу (DeepPavlov ner_rus_bert, Apache-2.0) — API может отличаться по версии,
проверить в Colab. Held-out test.jsonl в обучении НЕ участвует.
"""
import os

import numpy as np
import torch
from datasets import Dataset
from seqeval.metrics import f1_score, precision_score, recall_score
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

HERE = os.path.dirname(os.path.abspath(__file__))
STUDENT = "cointegrated/rubert-tiny2"
SILVER_WEIGHT = 0.3
LABELS = ["O", "B-PERSON", "I-PERSON"]
L2I = {l: i for i, l in enumerate(LABELS)}
I2L = {i: l for l, i in L2I.items()}

tokenizer = AutoTokenizer.from_pretrained(STUDENT)


def read_conll(path, weight):
    """CoNLL (token\ttag, пустая строка = граница предложения) -> примеры с весом."""
    examples, toks, tags = [], [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                if toks:
                    examples.append({"tokens": toks, "ner_tags": [L2I.get(t, 0) for t in tags],
                                     "weight": weight})
                    toks, tags = [], []
                continue
            parts = line.split("\t")
            toks.append(parts[0])
            tags.append(parts[1] if len(parts) > 1 else "O")
    if toks:
        examples.append({"tokens": toks, "ner_tags": [L2I.get(t, 0) for t in tags],
                         "weight": weight})
    return examples


def tokenize_and_align(batch):
    enc = tokenizer(batch["tokens"], truncation=True, is_split_into_words=True,
                    max_length=128)
    labels = []
    for i, tags in enumerate(batch["ner_tags"]):
        word_ids = enc.word_ids(batch_index=i)
        prev, lab = None, []
        for wid in word_ids:
            if wid is None:
                lab.append(-100)
            elif wid != prev:
                lab.append(tags[wid])
            else:                       # продолжение слова — субтокены не учим
                lab.append(-100)
            prev = wid
        labels.append(lab)
    enc["labels"] = labels
    enc["weight"] = batch["weight"]
    return enc


class WeightedTrainer(Trainer):
    """CE-loss на токен, домноженный на вес примера (gold=1.0, silver=0.3)."""

    def compute_loss(self, model, inputs, return_outputs=False, **kw):
        weights = inputs.pop("weight")
        labels = inputs["labels"]
        outputs = model(**{k: v for k, v in inputs.items() if k != "labels"})
        logits = outputs.logits
        loss_fct = torch.nn.CrossEntropyLoss(reduction="none")
        per_tok = loss_fct(logits.view(-1, len(LABELS)), labels.view(-1))
        per_tok = per_tok.view(labels.shape)              # (batch, seq)
        mask = (labels != -100).float()
        w = weights.to(per_tok.dtype).unsqueeze(1)         # (batch, 1)
        loss = (per_tok * mask * w).sum() / mask.sum().clamp(min=1)
        return (loss, outputs) if return_outputs else loss


def compute_metrics(p):
    preds = np.argmax(p.predictions, axis=2)
    true_lab, pred_lab = [], []
    for pred, lab in zip(preds, p.label_ids):
        t = [I2L[l] for l in lab if l != -100]
        pr = [I2L[pp] for pp, l in zip(pred, lab) if l != -100]
        true_lab.append(t)
        pred_lab.append(pr)
    prec = precision_score(true_lab, pred_lab)
    rec = recall_score(true_lab, pred_lab)
    f1 = f1_score(true_lab, pred_lab)
    f2 = (5 * prec * rec / (4 * prec + rec)) if (4 * prec + rec) else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "f2": f2}


def build(paths_weights):
    ex = []
    for path, w in paths_weights:
        if os.path.exists(path):
            ex += read_conll(path, w)
        else:
            print(f"! пропущен (нет файла): {path}")
    ds = Dataset.from_list(ex)
    return ds.map(tokenize_and_align, batched=True, remove_columns=["tokens", "ner_tags"])


def main():
    train_ds = build([
        (os.path.join(HERE, "train", "train.conll"), 1.0),
        (os.path.join(HERE, "train", "train_negatives.conll"), 1.0),
        (os.path.join(HERE, "silver", "corpus.conll"), SILVER_WEIGHT),
    ])
    dev_ds = build([
        (os.path.join(HERE, "dev", "dev.conll"), 1.0),
        (os.path.join(HERE, "dev", "dev_negatives.conll"), 1.0),
    ])
    model = AutoModelForTokenClassification.from_pretrained(
        STUDENT, num_labels=len(LABELS), id2label=I2L, label2id=L2I)

    args = TrainingArguments(
        output_dir=os.path.join(HERE, "person_ruBERT_distilled"),
        num_train_epochs=12,
        per_device_train_batch_size=32,
        per_device_eval_batch_size=64,
        learning_rate=5e-5,
        eval_strategy="epoch",
        save_strategy="epoch",
        metric_for_best_model="f2",
        greater_is_better=True,
        load_best_model_at_end=True,
        logging_steps=50,
        seed=2026,
    )
    trainer = WeightedTrainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=dev_ds,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_metrics,
    )
    trainer.train()
    out = os.path.join(HERE, "person_ruBERT_distilled")
    trainer.save_model(out)
    tokenizer.save_pretrained(out)
    print("Готово. Модель в", out, "— прогнать приёмку (см. DISTILLATION_RECIPE.md §6).")


def label_silver_with_teacher(corpus_txt=None, out_conll=None):
    """Разметить silver/corpus.txt учителем (DeepPavlov) -> silver/corpus.conll.

    Запустить ОТДЕЛЬНО в Colab до main():
        pip install deeppavlov && python -m deeppavlov install ner_rus_bert
    API DeepPavlov зависит от версии — проверить формат возврата (токены, теги).
    """
    from deeppavlov import build_model
    corpus_txt = corpus_txt or os.path.join(HERE, "silver", "corpus.txt")
    out_conll = out_conll or os.path.join(HERE, "silver", "corpus.conll")
    teacher = build_model("ner_rus_bert", download=True)
    lines = [ln.strip() for ln in open(corpus_txt, encoding="utf-8") if ln.strip()]
    with open(out_conll, "w", encoding="utf-8") as f:
        for i in range(0, len(lines), 64):
            batch = lines[i:i + 64]
            batch_tokens, batch_tags = teacher(batch)
            for toks, tags in zip(batch_tokens, batch_tags):
                prev = "O"
                for w, t in zip(toks, tags):
                    is_per = t.endswith("PER")
                    tag = ("B-PERSON" if prev != "PERSON" else "I-PERSON") if is_per else "O"
                    prev = "PERSON" if is_per else "O"
                    f.write(f"{w}\t{tag}\n")
                f.write("\n")
    print("silver-метки записаны:", out_conll)


if __name__ == "__main__":
    main()
