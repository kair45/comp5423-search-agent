"""Inspect saved, reference-blind rankings at multiple depths and original documents."""
import json
import sys
from pathlib import Path
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"code"))
from searchkit.runs import normalized,records
from searchkit.store import Store
from searchkit.agent import atomic_text
data=ROOT/"data"; out=ROOT/"runs/validation-retrieval"
cases=records(out/"retrieval-queries.jsonl")
refs={r["id"]:normalized(r["answer"]) for r in records(data/"validation/validation.jsonl")}
store=Store(data/"index")
@lru_cache(32)
def text(i):
    return " "+normalized(store.get(i)[0])+" "
methods=["bm25","e5","qwen","fusion"]
stats={m:{"doc":[0,0,0],"passage":[0,0,0]} for m in methods}
examples=[]
for case in cases:
    ref=" "+refs[case["id"]]+" "
    for m in methods:
        docpos=passpos=None
        for pos,i in enumerate(case["rankings"][m],1):
            if docpos is None and ref in text(i):docpos=pos
            parts=case["documents"][i]["snippets"]
            if m in ["bm25","qwen"]:parts=parts[:1]
            if passpos is None and any(ref in " "+normalized(p["quote"])+" " for p in parts):passpos=pos
        for ix,k in enumerate((1,3,5)):
            stats[m]["doc"][ix]+=int(docpos is not None and docpos<=k)
            stats[m]["passage"][ix]+=int(passpos is not None and passpos<=k)
        if m=="fusion" and docpos and not passpos:
            examples.append({"question_id":case["id"],"source":case["rankings"][m][docpos-1],"rank":docpos})
atomic_text(out/"coverage-by-depth.json",json.dumps({"n":len(cases),"methods":stats,"document_only_examples":examples},indent=2))
print(stats,flush=True)
