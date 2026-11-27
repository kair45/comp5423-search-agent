"""CLI for index building, inspection, experiments, generation and validation."""
import argparse
import json
from pathlib import Path

from searchkit.agent import CONFIGS, atomic_text, dumps
from searchkit.store import build_store

ROOT=Path(__file__).resolve().parent.parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,default=ROOT/"data")
    sub=p.add_subparsers(dest="command",required=True)
    index=sub.add_parser("index"); index.add_argument("stage",choices=["bm25","e5","qwen"]); index.add_argument("--source",type=Path)
    index.add_argument("--expected",type=int,default=100195); index.add_argument("--windows",type=int,default=2); index.add_argument("--batch-size",type=int,default=32)
    search=sub.add_parser("search"); search.add_argument("query"); search.add_argument("--methods",default="bm25,e5,qwen"); search.add_argument("--top",type=int,default=5)
    read=sub.add_parser("read"); read.add_argument("docid"); read.add_argument("--focus",default="");read.add_argument("--start",type=int)
    ask=sub.add_parser("ask"); ask.add_argument("question"); ask.add_argument("--trace",type=Path)
    batch=sub.add_parser("batch"); batch.add_argument("input",type=Path); batch.add_argument("output",type=Path); batch.add_argument("--limit",type=int)
    for sp in (batch,ask):
        sp.add_argument("--profile",choices=CONFIGS,default="F");sp.add_argument("--budget",type=int,default=8)
    check=sub.add_parser("verify");check.add_argument("questions",type=Path);check.add_argument("predictions",type=Path);check.add_argument("--expected",type=int,default=100)
    evaluate=sub.add_parser("score"); evaluate.add_argument("validation",type=Path);evaluate.add_argument("predictions",type=Path)
    exp=sub.add_parser("experiment");exp.add_argument("validation",type=Path);exp.add_argument("output",type=Path);exp.add_argument("--profiles",default="ABCDEF");exp.add_argument("--budget",type=int,default=8)
    exp.add_argument("--reuse-profiles",default="",help="Score existing, verified control predictions for these profiles instead of rerunning them.")
    for sp in (batch,evaluate,exp): sp.add_argument("--split",choices=["all","dev","holdout"],default="holdout" if sp is exp else "all")
    a=p.parse_args(); data=a.data; cmd=a.command
    if cmd=="index":
        source=a.source or data/"corpus"
        if a.stage=="bm25": return build_store(source,data/"index/documents.sqlite",a.expected)
        from searchkit.dense import make_e5,import_qwen
        if a.stage=="e5": return make_e5(data,source,a.windows,a.batch_size)
        return import_qwen(data,source)
    from searchkit.retrieval import Retrieval
    from searchkit.runs import Agent,Provider,SKILLS,questions,run_batch,score,verify
    if cmd=="search": result=Retrieval(data,a.methods.split(",")).search(a.query,top=a.top)
    elif cmd=="read": result=Retrieval(data,("bm25",)).store.read(a.docid,a.focus,a.start)
    elif cmd=="ask":
        agent=Agent(Retrieval(data,CONFIGS[a.profile][0]),Provider(),SKILLS,a.profile,a.budget)
        result=agent.run("interactive",a.question,notify=lambda n,r: print("Tool:",n,flush=True))
        if a.trace: atomic_text(a.trace,dumps(result)+"\n")
        print(result["answer"]);return
    elif cmd=="batch":
        items=questions(a.input,a.split)
        if a.limit is not None: items=items[:a.limit]
        run_batch(data,items,a.output,a.profile,a.budget);return
    elif cmd=="verify":
        items=questions(a.questions)
        if len(items)!=a.expected: raise ValueError(f"Expected {a.expected} questions")
        result={"valid":len(verify(a.predictions,items))}
    elif cmd=="score": result=score(a.predictions,a.validation,a.split)
    else:
        result={}; a.output.mkdir(parents=True,exist_ok=True)
        for profile in a.profiles:
            out=a.output/(profile+".jsonl")
            if profile not in a.reuse_profiles or not out.is_file():
                run_batch(data,questions(a.validation,a.split),out,profile,a.budget)
            result[profile]=score(out,a.validation,a.split)
            atomic_text(a.output/"metrics.json",dumps(result))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
