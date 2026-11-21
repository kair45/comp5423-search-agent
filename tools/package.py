"""Create a source archive or verify and assemble the course submission."""
import argparse
import json
from pathlib import Path
import re
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"code"))
from searchkit.runs import verify,questions

def main():
    p=argparse.ArgumentParser();p.add_argument("--group");p.add_argument("--source-only",action="store_true");a=p.parse_args()
    dest=ROOT/"deliverables";dest.mkdir(exist_ok=True)
    extras={}
    if a.source_only: name="Source.zip"
    else:
        if not a.group or not re.fullmatch("[A-Za-z0-9-]+",a.group): raise ValueError("Supply the actual group number")
        name="Group-"+a.group+".zip"
        test=ROOT/"data/test.jsonl";pred=dest/"test_prediction.jsonl";items=questions(test)
        if len(items)!=100:raise ValueError("Expected 100 course test items")
        verify(pred,items)
        extras={"test_prediction.jsonl":pred}
        for part,suffix in (("Report","pdf"),("Video","mp4")):
            filename=f"Group-{a.group}-{part}.{suffix}"; extras[filename]=dest/filename
        for path in extras.values():
            if not path.is_file() or not path.stat().st_size:raise ValueError("Missing deliverable: "+str(path))
    files={p.relative_to(ROOT).as_posix():p for p in (ROOT/"code").rglob("*") if p.is_file() and "__pycache__" not in p.parts and
           (p.suffix in (".py",".ps1",".md",".json") or p.name in ("requirements.txt",".env.example"))}
    for expected in ("code/README.md","code/main.py","code/requirements.txt","code/skills/follow-clues/SKILL.md","code/skills/resolve-entity/SKILL.md"):
        if expected not in files:raise ValueError("Missing "+expected)
    final=dest/name;tmp=final.with_suffix(".tmp")
    with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for arc,path in sorted({**files,**extras}.items()):z.write(path,arc)
    with zipfile.ZipFile(tmp) as z:
        if z.testzip() is not None or set(z.namelist())!=set(files)|set(extras):raise ValueError("Archive integrity failed")
    tmp.replace(final);print(final)
if __name__=="__main__":main()
