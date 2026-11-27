"""Validation, normalization and resumable question-level execution."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from threading import local
import hashlib
import json
from pathlib import Path
import random
import re
import string

from filelock import FileLock

from .agent import CONFIGS, Agent, atomic_text, dumps
from .provider import Provider
from .retrieval import Retrieval

SKILLS=Path(__file__).resolve().parents[1]/"skills"

def records(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        return [json.loads(s) for s in f if s.strip()]

def questions(path,split="all"):
    rows=records(path); result=[]; used=set()
    for r in rows:
        if not isinstance(r.get("id"),str) or not isinstance(r.get("question"),str) or not r["question"].strip():
            raise ValueError("Missing string id or question")
        if r["id"] in used: raise ValueError("Duplicate question ID")
        used.add(r["id"]); result.append((r["id"],r["question"]))
    if split!="all":
        if len(result)!=100: raise ValueError("The course development split requires exactly 100 validation questions")
        shuffled=sorted(used); random.Random(5423).shuffle(shuffled)
        ids=set(shuffled[:70] if split=="dev" else shuffled[70:])
        result=[pair for pair in result if pair[0] in ids]
    return result

def normalized(s):
    s=s.lower().translate(str.maketrans("","",string.punctuation))
    return " ".join(re.sub(r"\b(a|an|the)\b"," ",s).split())

def validate(record,ident,question):
    fields={"id","question","answer","trajectory","tool_calls","total_tokens"}
    if set(record)!=fields or (record["id"],record["question"])!=(ident,question):
        raise ValueError("Prediction identity or schema mismatch: "+ident)
    trace=record["trajectory"]; answer=record["answer"]
    if not isinstance(trace,list) or not isinstance(answer,str) or not answer.strip(): raise ValueError("Invalid answer or trajectory")
    if len(trace)<4 or trace[0].get("role")!="system" or trace[1].get("role")!="user" or trace[1].get("content")!=question:
        raise ValueError("Missing original prompt or question")
    pending={}; n=0; tokens=0; searched=False; seen=set(); found=False
    for step in trace:
        if step.get("event")=="context": continue
        role=step["role"]
        if role=="assistant":
            if pending: raise ValueError("Unanswered calls in trace")
            value=step["usage"]["total_tokens"]
            if type(value)!=int or value<0: raise ValueError("Invalid usage")
            tokens+=value
            if step.get("api",{}).get("finish_reason")=="length": continue
            for call in step.get("tool_calls") or []:
                cid=call["id"]; name=call["function"]["name"]; json.loads(call["function"]["arguments"])
                if not isinstance(cid,str) or not cid or cid in seen: raise ValueError("Duplicate or missing tool-call ID")
                seen.add(cid);pending[cid]=name; n+=1
        elif role=="tool":
            name=pending.pop(step["tool_call_id"],None)
            if name!=step.get("name") or name is None: raise ValueError("Invalid tool/result pairing")
            response=json.loads(step["content"])
            if name=="search" and "results" in response: searched=True
    if (not searched or pending or trace[-1].get("role")!="assistant" or trace[-1].get("content")!=answer
            or type(record["tool_calls"])!=int or type(record["total_tokens"])!=int
            or record["tool_calls"]!=n or record["total_tokens"]!=tokens):
        raise ValueError("Bad final answer, accounting or tool trace: "+ident)

def verify(path,items):
    rows=records(path); lookup={r["id"]:r for r in rows}
    if len(rows)!=len(items) or set(lookup)!={i for i,q in items}: raise ValueError("Missing, extra or repeated predictions")
    for ident,q in items: validate(lookup[ident],ident,q)
    return lookup

def run_batch(data,items,out,profile,budget):
    if not items: raise ValueError("Empty input")
    provider=Provider(); retrieval=Retrieval(data,CONFIGS[profile][0])
    workers=int(os.environ.get("COMP5423_WORKERS","1"))
    if not 1<=workers<=12: raise ValueError("COMP5423_WORKERS must be between 1 and 12")
    thread_state=local()
    out=Path(out); out.parent.mkdir(parents=True,exist_ok=True)
    job=out.parent/(out.name+".state"); job.mkdir(exist_ok=True)
    fingerprint={"questions":hashlib.sha256(dumps(items).encode()).hexdigest(),"model":provider.model,"endpoint":provider.base,
                 "profile":profile,"budget":budget,"corpus":retrieval.store.corpus_id,
                 "indexes":{m:json.loads((Path(data)/"index"/(m+".json")).read_text(encoding="utf-8"))["base"] for m in retrieval.methods if m!="bm25"}}
    files=sorted(list(Path(__file__).parent.glob("*.py"))+list(SKILLS.glob("*/SKILL.md")))
    fingerprint["implementation"]=hashlib.sha256(b"".join(f.read_bytes() for f in files)).hexdigest()
    with FileLock(str(job/"run.lock"),timeout=0):
        manifest=job/"manifest.json"
        if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))!=fingerprint:
            raise ValueError("Run inputs/config changed. Choose a new output file.")
        if not manifest.exists() and out.exists(): raise FileExistsError("Untracked output already exists")
        atomic_text(manifest,dumps(fingerprint))
        def predict(item):
            ident,q=item
            if not hasattr(thread_state,"agent"):
                thread_state.agent=Agent(retrieval,Provider(),SKILLS,profile,budget)
            path=job/(hashlib.sha256(ident.encode()).hexdigest()+".json")
            state=json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            row=thread_state.agent.run(ident,q,state,lambda s:atomic_text(path,dumps(s)))
            validate(row,ident,q)
            return row
        pool=ThreadPoolExecutor(max_workers=workers)
        futures={}
        try:
            futures={pool.submit(predict,item):i for i,item in enumerate(items)}
            complete=[None]*len(items)
            for count,future in enumerate(as_completed(futures),1):
                row=future.result()
                complete[futures[future]]=row
                print(f"{count}/{len(items)} {row['id']} calls={row['tool_calls']} tokens={row['total_tokens']}",flush=True)
        finally:
            pool.shutdown(wait=True,cancel_futures=True)
            retrieval.rank_cached.cache_clear()
            retrieval.store.con.close()
            retrieval.dense.clear()
        atomic_text(out,"".join(dumps(r)+"\n" for r in complete))
        verify(out,items)
    return complete

def score(pred,validation,split):
    items=questions(validation,split); rows=verify(pred,items)
    answers={r["id"]:r["answer"] for r in records(validation)}
    correct=sum(normalized(row["answer"])==normalized(answers[i]) for i,row in rows.items())
    return {"questions":len(items),"correct":correct,"normalized_em_percent":round(correct*100/len(items),2),
            "tool_calls":sum(r["tool_calls"] for r in rows.values()),"total_tokens":sum(r["total_tokens"] for r in rows.values())}
