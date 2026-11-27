"""Generate a template-based draft or signed group report using observed data."""
import argparse
import json
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"code"))
from searchkit.runs import records,questions,verify,normalized
from searchkit.agent import atomic_text
REPORT=ROOT/"report"

def tex(x):
    table={"\\":r"\textbackslash{}","{":r"\{","}":r"\}","&":r"\&","_":r"\_","#":r"\#","%":r"\%","$":r"\$","~":r"\textasciitilde{}","^":r"\textasciicircum{}"}
    return "".join(table.get(c,c) for c in str(x))

def group_info(path):
    if not path: return None
    g=json.loads(path.read_text(encoding="utf-8-sig"))
    if not re.fullmatch(r"[A-Za-z0-9-]+",str(g["group"])): raise ValueError("Invalid group identifier")
    members=g["members"]
    if len(members) not in (3,4) or sum(Decimal(str(m["percent"])) for m in members)!=100 or any(Decimal(str(m["percent"]))<0 for m in members):
        raise ValueError("Check group size and contribution percentages")
    for i,m in enumerate(members,1):
        if not str(m["name"]).strip() or not str(m["role"]).strip(): raise ValueError("Each member needs a real name and contribution")
        source=(path.parent/m["signature"]).resolve()
        if source.suffix.lower() not in {".png",".jpg",".pdf"} or not source.is_file(): raise ValueError("Missing member-supplied signature")
        dest=REPORT/"figures"/(f"member-{i}"+source.suffix.lower())
        if source!=dest:shutil.copyfile(source,dest)
        m["figure"]=dest.relative_to(REPORT).as_posix()
    return g

def declare(group):
    original=(REPORT/"contributions-template.tex").read_text(encoding="utf-8")
    decl=original.split(r"\subsection*{Declaration}",1)[1].split(r"\begin{center}",1)[0]
    decl=decl.replace("Group X","Group "+tex(group["group"]) if group else "the project group")
    if not group:
        roles="Pending the members' names, their actual roles and agreed percentages."
        signatures=r"\noindent Signatures pending. The sample signature from the course template has been omitted."
    else:
        roles=r"\begin{itemize}"+"\n"+"\n".join(r"\item "+tex(m["name"])+" ("+tex(str(m["percent"])+"%")+") "+tex(m["role"]) for m in group["members"])+"\n"+r"\end{itemize}"
        signatures="\n".join(r"\noindent\includegraphics[height=0.8cm,keepaspectratio]{"+m["figure"]+"} "+tex(m["name"])+r"\par" for m in group["members"])
    return r"\section*{CONTRIBUTION AND DECLARATION}\subsection*{Contribution}"+"\n"+roles+"\n"+r"\subsection*{Declaration}"+"\n"+decl+"\n"+signatures

def main():
    p=argparse.ArgumentParser();p.add_argument("--group",type=Path);p.add_argument("--metrics",type=Path);p.add_argument("--cases",type=Path)
    p.add_argument("--engine",default="pdflatex");p.add_argument("--output",type=Path,default=ROOT/"deliverables/Project-Report-Draft.pdf")
    a=p.parse_args();group=group_info(a.group)
    data=ROOT/"data";diag=ROOT/"runs/validation-retrieval"
    met=json.loads((diag/"retrieval-metrics.json").read_text(encoding="utf-8"))
    rows=records(diag/"retrieval-queries.jsonl");ref={r["id"]:normalized(r["answer"]) for r in records(data/"validation/validation.jsonl")}
    def hit(row,method):
        for docid in row["rankings"][method]:
            passages=row["documents"][docid]["snippets"]
            for piece in (passages if method in ("e5","fusion") else passages[:1]):
                if " "+ref[row["id"]]+" " in " "+normalized(piece["quote"])+" ": return docid
        return None
    gain=[r["id"] for r in rows if hit(r,"fusion") and not hit(r,"bm25")]
    loss=[r["id"] for r in rows if hit(r,"bm25") and not hit(r,"fusion")]
    interp=f"Compared with BM25 on identical questions, fusion gained {len(gain)} coverage hits and lost {len(loss)}."
    if gain: interp+=" A gain can be inspected under validation ID "+tex(gain[0])+"."
    if loss: interp+=" A counterexample is ID "+tex(loss[0])+"."
    config="No paid-model holdout results are available in this draft; answer EM, tool-call efficiency and API token consumption remain unmeasured."
    if a.metrics:
        m=json.loads(a.metrics.read_text(encoding="utf-8"));config=r"\par\smallskip\begin{tabular}{lrrr}\toprule Config. & EM (\%) & Calls & Tokens\\\midrule "+"\n"
        for key,obj in m.items():config+=f"{tex(key)} & {obj['normalized_em_percent']:.2f} & {obj['tool_calls']} & {obj['total_tokens']}"+r"\\"+"\n"
        config+=r"\bottomrule\end{tabular}\par"
        if all(k in m for k in "ABCDE"):
            a0,b,c,d,e=(m[k] for k in "ABCDE")
            config+=(f" On the same {e['questions']} questions, switching from lexical search to rank fusion "
                     f"changed the correct-answer count from {a0['correct']} to {b['correct']}. "
                     f"Allowing iteration yielded {c['correct']} correct. With compact context, "
                     f"the agent answered {d['correct']} correctly. Enabling the skills produced {e['correct']}. "
                     f"Mean token use per question was {d['total_tokens']/d['questions']:,.0f} for D "
                     f"and {e['total_tokens']/e['questions']:,.0f} for E. "
                     "A difference of one correct answer moves EM by 3.33 percentage points on this split.")
    obs="Real selection examples require recorded agent runs; the retrieval-only experiment does not exercise either procedure."
    if a.cases:
        val=verify(a.cases,questions(data/"validation/validation.jsonl","holdout"))
        byskill={}
        selections={}
        for row in val.values():
            for s in row["trajectory"]:
                if s.get("role")=="tool" and s["name"]=="load_skill":
                    n=json.loads(s["content"]).get("name")
                    if n and n not in byskill:byskill[n]=row["id"]
                    if n:selections.setdefault(row["id"],set()).add(n)
        if byskill: obs="Observed validation decisions: "+", ".join(tex(n)+" on question "+tex(i) for n,i in byskill.items())+"."
        else: obs="No skill loads occurred in this recorded holdout run."
        without=[ident for ident in val if ident not in selections]
        if selections and without:
            obs+=f" In all, {len(selections)} of {len(val)} questions loaded a skill. Question {tex(without[0])} ran without loading either procedure."
        test_file=ROOT/"deliverables/test_prediction.jsonl"
        if test_file.exists():
            test=verify(test_file,questions(data/"test.jsonl"))
            examples={}
            for row in test.values():
                for step in row["trajectory"]:
                    if step.get("role")=="tool" and step["name"]=="load_skill":
                        name=json.loads(step["content"]).get("name")
                        if name:examples.setdefault(name,[]).append(row["id"])
            for name,ids in sorted(examples.items()):
                obs+=f" In the separate test set, {tex(name)} was loaded on {len(set(ids))} distinct questions (for example, ID {tex(ids[0])})."
            if "resolve-entity" not in examples and "resolve-entity" not in byskill:
                obs+=" Neither recorded evaluation demonstrated automatic loading of resolve-entity."
        correct_ids=[i for i,row in val.items() if normalized(row["answer"])==ref[i]]
        missed_ids=[i for i in val if i not in correct_ids]
        if correct_ids and missed_ids and a.metrics:
            good,miss=val[correct_ids[0]],val[missed_ids[0]]
            config+=(f" On validation question {tex(good['id'])}, E matched the reference using {good['tool_calls']} tool requests. "
                     f"On {tex(miss['id'])}, {miss['tool_calls']} requests produced a different answer.")
    completed=bool(group and a.metrics and a.cases)
    macros={"ReportGroup":"Group "+tex(group["group"]) if group else "Group details pending",
      "RunStatus":"Provider experiments are reported below." if a.metrics else "The measured experiment here evaluates retrieval on all 100 validation questions; end-to-end API results are pending.",
      "StatusFooter":"" if completed else "This copy is a draft.",
      "ECount":f"{json.loads((data/'index/e5.json').read_text())['vectors']:,}",
      "RetrievalRows":"\n".join(label+" & "+str(met["hits"][k])+" & "+str(met["questions"])+r"\\" for k,label in [("bm25","BM25"),("e5","Multilingual E5"),("qwen","Qwen3-Embedding"),("fusion","Rank fusion")]),
      "RetrievalInterpretation":interp,"SkillObservations":obs,"AgentMetrics":config}
    atomic_text(REPORT/"generated.tex","\n".join(r"\newcommand{\%s}{%s}"%(k,v) for k,v in macros.items()))
    atomic_text(REPORT/"contributions.tex",declare(group))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    for i in range(2):
        result=subprocess.run([a.engine,"-interaction=nonstopmode","-halt-on-error","-no-shell-escape","main.tex"],cwd=REPORT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if result.returncode:
            print(result.stdout.decode(errors="replace")[-4000:]);raise SystemExit(result.returncode)
    shutil.copyfile(REPORT/"main.pdf",a.output)
    print(a.output)
if __name__=="__main__":main()
