"""Reference-blind retrieval followed by answer-string coverage diagnostics."""
from pathlib import Path
import json
import time
from .agent import atomic_text,dumps
from .retrieval import Retrieval
from .runs import records,normalized

def evaluate(data,validation,out):
    out=Path(out); out.mkdir(exist_ok=True,parents=True)
    engine=Retrieval(data)
    rows=records(validation)
    saved=out/"retrieval-queries.jsonl"
    cache={r["id"]:r for r in records(saved)} if saved.exists() else {}
    for idx,row in enumerate(rows,1):
        if row["id"] in cache: continue
        start=time.monotonic()
        query=row["question"]
        # Take the union of three single-method top fives and the fusion top five.
        # Ask each model once and reuse identical ranked candidates to compare fairly.
        from collections import defaultdict
        from .store import locate
        from .dense import Dense
        candidates={}; scores=defaultdict(float); primary={}
        for method in ("bm25","e5","qwen"):
            if method=="bm25": found=[(i,s,None) for i,s in engine.store.sparse(query,30)]
            else:
                if method not in engine.dense:engine.dense[method]=Dense(data,method,engine.store.corpus_id)
                found=engine.dense[method].search(query,30)
            candidates[method]=[i for i,_,_ in found[:5]]
            for rank,(docid,s,span) in enumerate(found,1):
                scores[docid]+=1/(60+rank)
                if span and span[1]>span[0]: primary[docid]=span
        candidates["fusion"]=sorted(scores,key=lambda i:(-scores[i],i))[:5]
        stored={}
        for i in dict.fromkeys(x for ls in candidates.values() for x in ls):
            text,url=engine.store.get(i); snippets=locate(text,query,1)
            if i in primary:
                l,r=primary[i]
                if not snippets or r<=snippets[0]["start"] or l>=snippets[0]["end"]:
                    snippets.append({"start":l,"end":r,"quote":text[l:r]})
            stored[i]={"url":url,"snippets":snippets}
        entry={"id":row["id"],"question":query,"rankings":candidates,"documents":stored,"seconds":round(time.monotonic()-start,2)}
        cache[row["id"]]=entry
        atomic_text(saved,"".join(dumps(x)+"\n" for x in cache.values()))
        if idx%5==0: print("Retrieval diagnostic",idx,flush=True)
    totals={m:0 for m in ("bm25","e5","qwen","fusion")}
    for row in rows:
        entry=cache[row["id"]]; answer=normalized(row["answer"])
        for method,ids in entry["rankings"].items():
            covered=any(" "+answer+" " in " "+normalized(p["quote"])+" " for i in ids for p in (entry["documents"][i]["snippets"] if method in ("e5","fusion") else entry["documents"][i]["snippets"][:1]))
            totals[method]+=int(bool(answer) and covered)
    result={"questions":len(rows),"metric":"normalized reference string in any returned passage, top 5 (not answer EM or document relevance)","hits":totals}
    atomic_text(out/"retrieval-metrics.json",json.dumps(result,indent=2));print(result,flush=True)
