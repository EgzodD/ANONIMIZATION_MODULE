"""
Изолированная оценка Natasha NER (только PERSON, без regex-распознавателей).
Разбивка: strict/partial, по падежам, по регистру, по формату ФИО, таксономия ошибок.
"""
import json
import os
import sys
import re
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rcParams
rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False

PROJ = "/media/egzod/01D7DA4662F24750/work/DENIS WORK/MY_PROJECTS/GLOBAL PROJECT/ANONIMIZATION_MODULE(work)"
sys.path.insert(0, PROJ)

# ── Изолируем Natasha: грузим только её, без AnalyzerEngine ──
from app.custom_recognizers import NatashaPersonRecognizer

natasha = NatashaPersonRecognizer()
natasha.load()

def natasha_persons(text):
    """Возвращает спаны PERSON только от Natasha."""
    res = natasha.analyze(text, entities=["PERSON"], nlp_artifacts=None)
    return [(r.start, r.end) for r in res]

OUTDIR = "/home/egzod/Рабочий стол/report_anonymization/Графики метрик"
os.makedirs(OUTDIR, exist_ok=True)
BLUE="#4472C4"; GREEN="#2E9E4F"; ORANGE="#E08A00"; RED="#C0392B"; GRAY="#7F7F7F"; DARKBLUE="#1F497D"; PURPLE="#7B5EA7"

import pymorphy3
morph = pymorphy3.MorphAnalyzer()
CASE_RU = {"nomn":"Имен.","gent":"Род.","datv":"Дат.","accs":"Вин.","ablt":"Твор.","loct":"Предл."}

def detect_case(name):
    """Определяет падеж имени по последнему значимому слову."""
    words = [w for w in re.split(r"[\s.]+", name) if len(w) > 1]
    if not words:
        return "?"
    for pp in morph.parse(words[-1]):
        if {"Surn","Name","Patr"} & pp.tag.grammemes:
            c = pp.tag.case
            if c: return c
    c = morph.parse(words[-1])[0].tag.case
    return c or "?"

def name_format(name):
    """Классифицирует формат имени."""
    if re.search(r"\b\w\.\w?\.?", name):
        return "Инициалы"
    n = len([w for w in re.split(r"\s+", name) if w])
    return {1:"1 слово", 2:"2 слова", 3:"3 слова"}.get(n, "3 слова")

test = [json.loads(l) for l in open(os.path.join(PROJ,"data/natasha_training/test/test.jsonl"),encoding="utf-8")]

def overlap(a,b): return not (a[1]<=b[0] or b[1]<=a[0])

# ════════════════════════════════════════════════════════════════════
#  СБОР
# ════════════════════════════════════════════════════════════════════
S = Counter()  # strict tp/fp/fn
P = Counter()  # partial tp/fp/fn
by_case   = defaultdict(lambda: Counter())   # падеж -> tp/fn (partial)
by_reg    = defaultdict(lambda: Counter())   # регистр
by_fmt    = defaultdict(lambda: Counter())   # формат
# таксономия MUC
muc = Counter()  # correct / partial / missing / spurious

for ex in test:
    gold = [(sp["start"], sp["stop"]) for sp in ex["spans"] if sp["type"]=="PERSON"]
    pred = natasha_persons(ex["text"])
    used_strict=set(); used_partial=set()

    for gs,ge in gold:
        name = ex["text"][gs:ge]
        case = detect_case(name); reg = "Со строчной" if name==name.lower() else "С заглавной"; fmt = name_format(name)

        # strict
        s_i = next((i for i,(ps,pe) in enumerate(pred) if ps==gs and pe==ge and i not in used_strict), None)
        if s_i is not None: S["tp"]+=1; used_strict.add(s_i)
        else: S["fn"]+=1

        # partial
        p_i = next((i for i,(ps,pe) in enumerate(pred) if overlap((gs,ge),(ps,pe)) and i not in used_partial), None)
        if p_i is not None:
            P["tp"]+=1; used_partial.add(p_i)
            by_case[case]["tp"]+=1; by_reg[reg]["tp"]+=1; by_fmt[fmt]["tp"]+=1
            # MUC: correct если границы точны, иначе partial
            ps,pe = pred[p_i]
            muc["correct" if (ps==gs and pe==ge) else "partial"]+=1
        else:
            P["fn"]+=1; muc["missing"]+=1
            by_case[case]["fn"]+=1; by_reg[reg]["fn"]+=1; by_fmt[fmt]["fn"]+=1

    # spurious: предсказания без пересечения с gold
    for i,(ps,pe) in enumerate(pred):
        if not any(overlap((ps,pe),(gs,ge)) for gs,ge in gold):
            P["fp"]+=1; S["fp"]+=1; muc["spurious"]+=1

def prf(c):
    tp,fp,fn=c["tp"],c["fp"],c["fn"]
    p=tp/(tp+fp) if tp+fp else 1.0
    r=tp/(tp+fn) if tp+fn else 1.0
    f=2*p*r/(p+r) if p+r else 0.0
    return p,r,f

# ════════════════════════════════════════════════════════════════════
#  КОНСОЛЬ
# ════════════════════════════════════════════════════════════════════
print("="*60)
print("ИЗОЛИРОВАННАЯ ОЦЕНКА NATASHA (только PERSON, без regex)")
print("="*60)
sp_,sr_,sf_=prf(S); pp_,pr_,pf_=prf(P)
print(f"\nSTRICT  (точные границы):  P={sp_*100:.1f}%  R={sr_*100:.1f}%  F1={sf_*100:.1f}%")
print(f"PARTIAL (перекрытие):     P={pp_*100:.1f}%  R={pr_*100:.1f}%  F1={pf_*100:.1f}%")
print(f"\nРазрыв strict/partial = {(pf_-sf_)*100:.1f} п.п. (ошибки границ)")

print("\n— Recall по падежам —")
case_order=["nomn","gent","datv","accs","ablt","loct"]
for c in case_order:
    cc=by_case.get(c)
    if cc and (cc['tp']+cc['fn']):
        r=cc['tp']/(cc['tp']+cc['fn'])
        print(f"  {CASE_RU[c]:<8} {cc['tp']:>3}/{cc['tp']+cc['fn']:<3} = {r*100:5.1f}%")

print("\n— Recall по регистру —")
for k,cc in by_reg.items():
    r=cc['tp']/(cc['tp']+cc['fn'])
    print(f"  {k:<14} {cc['tp']:>3}/{cc['tp']+cc['fn']:<3} = {r*100:5.1f}%")

print("\n— Recall по формату ФИО —")
for k in ["1 слово","2 слова","3 слова","Инициалы"]:
    cc=by_fmt.get(k)
    if cc and (cc['tp']+cc['fn']):
        r=cc['tp']/(cc['tp']+cc['fn'])
        print(f"  {k:<10} {cc['tp']:>3}/{cc['tp']+cc['fn']:<3} = {r*100:5.1f}%")

print("\n— Таксономия ошибок (MUC) —")
tot_muc=sum(muc.values())
for k in ["correct","partial","missing","spurious"]:
    nm={"correct":"Точно","partial":"Частично","missing":"Пропущено","spurious":"Выдумано"}[k]
    print(f"  {nm:<12} {muc[k]:>3}  ({muc[k]/tot_muc*100:.1f}%)")

# ════════════════════════════════════════════════════════════════════
#  ГРАФИКИ
# ════════════════════════════════════════════════════════════════════
# N1 — strict vs partial (P/R/F1)
fig,ax=plt.subplots(figsize=(9,6))
groups=["Precision","Recall","F1"]; x=np.arange(3); w=0.36
sv=[sp_*100,sr_*100,sf_*100]; pv=[pp_*100,pr_*100,pf_*100]
ax.bar(x-w/2,sv,w,label="Strict (точные границы)",color=PURPLE,edgecolor="white")
ax.bar(x+w/2,pv,w,label="Partial (перекрытие)",color=GREEN,edgecolor="white")
for i in range(3):
    ax.text(i-w/2,sv[i]+1,f"{sv[i]:.1f}",ha="center",fontsize=10,fontweight="bold")
    ax.text(i+w/2,pv[i]+1,f"{pv[i]:.1f}",ha="center",fontsize=10,fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels(groups); ax.set_ylim(0,112); ax.set_ylabel("%")
ax.set_title("Natasha PERSON: strict vs partial\n(разрыв = ошибки границ имени)",
             fontsize=13,fontweight="bold",color=DARKBLUE,pad=15)
ax.legend(fontsize=10); ax.grid(axis="y",alpha=0.25); ax.spines[["top","right"]].set_visible(False)
plt.tight_layout(); plt.savefig(os.path.join(OUTDIR,"N1_natasha_strict_partial.png"),dpi=150,bbox_inches="tight"); plt.close()

# N2 — recall по падежам
fig,ax=plt.subplots(figsize=(10,6))
labels=[CASE_RU[c] for c in case_order if by_case.get(c)]
vals=[by_case[c]['tp']/(by_case[c]['tp']+by_case[c]['fn'])*100 for c in case_order if by_case.get(c)]
colors=[GREEN if v>=95 else (ORANGE if v>=85 else RED) for v in vals]
bars=ax.bar(labels,vals,color=colors,edgecolor="white")
for bar,c in zip(bars,[c for c in case_order if by_case.get(c)]):
    cc=by_case[c]; ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+1.5,
        f"{bar.get_height():.0f}%\n{cc['tp']}/{cc['tp']+cc['fn']}",ha="center",fontsize=9,fontweight="bold")
ax.set_ylim(0,115); ax.set_ylabel("Recall, %")
ax.set_title("Natasha: recall по падежам имён\n(ключевая способность — понимание склонений)",
             fontsize=13,fontweight="bold",color=DARKBLUE,pad=15)
ax.grid(axis="y",alpha=0.25); ax.spines[["top","right"]].set_visible(False)
plt.tight_layout(); plt.savefig(os.path.join(OUTDIR,"N2_natasha_падежи.png"),dpi=150,bbox_inches="tight"); plt.close()

# N3 — формат ФИО + регистр (две панели)
fig,(a1,a2)=plt.subplots(1,2,figsize=(13,6))
fmt_order=[k for k in ["1 слово","2 слова","3 слова","Инициалы"] if by_fmt.get(k)]
fv=[by_fmt[k]['tp']/(by_fmt[k]['tp']+by_fmt[k]['fn'])*100 for k in fmt_order]
fc=[GREEN if v>=95 else (ORANGE if v>=85 else RED) for v in fv]
b=a1.bar(fmt_order,fv,color=fc,edgecolor="white")
for bar,k in zip(b,fmt_order):
    cc=by_fmt[k]; a1.text(bar.get_x()+bar.get_width()/2,bar.get_height()+1.5,
        f"{bar.get_height():.0f}%\n{cc['tp']}/{cc['tp']+cc['fn']}",ha="center",fontsize=9,fontweight="bold")
a1.set_ylim(0,115); a1.set_ylabel("Recall, %"); a1.set_title("По формату ФИО",fontsize=12,fontweight="bold",color=DARKBLUE)
a1.grid(axis="y",alpha=0.25); a1.spines[["top","right"]].set_visible(False)

rk=list(by_reg.keys())
rv=[by_reg[k]['tp']/(by_reg[k]['tp']+by_reg[k]['fn'])*100 for k in rk]
rc=[GREEN if v>=95 else ORANGE for v in rv]
b=a2.bar(rk,rv,0.5,color=rc,edgecolor="white")
for bar,k in zip(b,rk):
    cc=by_reg[k]; a2.text(bar.get_x()+bar.get_width()/2,bar.get_height()+1.5,
        f"{bar.get_height():.0f}%\n{cc['tp']}/{cc['tp']+cc['fn']}",ha="center",fontsize=9,fontweight="bold")
a2.set_ylim(0,115); a2.set_title("По регистру",fontsize=12,fontweight="bold",color=DARKBLUE)
a2.grid(axis="y",alpha=0.25); a2.spines[["top","right"]].set_visible(False)
plt.suptitle("Natasha PERSON: разрезы по формату и регистру",fontsize=14,fontweight="bold",color=DARKBLUE)
plt.tight_layout(); plt.savefig(os.path.join(OUTDIR,"N3_natasha_формат_регистр.png"),dpi=150,bbox_inches="tight"); plt.close()

# N4 — таксономия ошибок (pie)
fig,ax=plt.subplots(figsize=(8,7))
order=["correct","partial","missing","spurious"]
nm={"correct":"Точно","partial":"Частично\n(ошибка границ)","missing":"Пропущено\n(утечка)","spurious":"Выдумано\n(over-mask)"}
cols={"correct":GREEN,"partial":ORANGE,"missing":RED,"spurious":PURPLE}
vals=[muc[k] for k in order]; labs=[f"{nm[k]}\n{muc[k]} ({muc[k]/sum(vals)*100:.1f}%)" for k in order]
ax.pie(vals,labels=labs,colors=[cols[k] for k in order],startangle=90,counterclock=False,
       wedgeprops={"edgecolor":"white","linewidth":2},textprops={"fontsize":11,"fontweight":"bold"})
ax.set_title("Natasha: таксономия результатов (MUC)",fontsize=14,fontweight="bold",color=DARKBLUE,pad=15)
plt.tight_layout(); plt.savefig(os.path.join(OUTDIR,"N4_natasha_ошибки.png"),dpi=150,bbox_inches="tight"); plt.close()

print("\nГрафики Natasha:")
for f in ["N1_natasha_strict_partial.png","N2_natasha_падежи.png","N3_natasha_формат_регистр.png","N4_natasha_ошибки.png"]:
    print(f"  {f}")
