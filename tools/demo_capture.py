"""Capture the running UI. Optional genuine JSONL supplies the final agent segment."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8514")
    parser.add_argument("--chrome");parser.add_argument("--ffmpeg",default="ffmpeg")
    parser.add_argument("--predictions",type=Path);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    figures=ROOT/"report/figures";figures.mkdir(exist_ok=True,parents=True)
    def font(size,bold=False):
        for name in (("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
                     ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")):
            try:return ImageFont.truetype(name,size)
            except OSError:continue
        return ImageFont.load_default()
    with tempfile.TemporaryDirectory() as temp,sync_playwright() as pw:
        work=Path(temp); slides=[]
        options={"headless":True}
        if args.chrome:options["executable_path"]=args.chrome
        br=pw.chromium.launch(**options)
        page=br.new_page(viewport={"width":1320,"height":820},device_scale_factor=1)
        page.set_default_timeout(90000)
        def slide(title,caption,seconds=7,figure=None):
            page.screenshot(path=str(work/"screen.png"),animations="disabled")
            source=Image.open(work/"screen.png").convert("RGB")
            if figure: source.save(figures/figure)
            canvas=Image.new("RGB",(1320,940),"#143044");canvas.paste(source,(0,0))
            d=ImageDraw.Draw(canvas);d.text((35,833),title,font=font(28,True),fill="white");d.text((35,879),caption,font=font(20),fill="#d5e5ee")
            filename=work/("frame%02d.png"%len(slides));canvas.save(filename);slides.append((filename,seconds))
        page.goto(args.url)
        page.get_by_role("button",name="Search and answer").wait_for()
        slide("Evidence Search | COMP5423","The interactive workspace and batch generator use the same document store and agent loop.",6,"interface.png")
        page.get_by_text("Explore the collection",exact=True).click()
        query="band member steel industry monopoly corruption charges company founder"
        page.get_by_role("textbox",name="Search query").fill(query)
        slide("Searching the fixed collection","This query combines clues from a public validation question; the answer field is never sent to retrieval.",6)
        page.get_by_role("button",name="Find evidence").click()
        page.get_by_role("heading",name="Document ",exact=False).first.wait_for(timeout=160000)
        slide("Three retrievers, one ranked list","Each result exposes the fusion score, rank contributions, original snippet and source URL.",8,"retrieval.png")
        page.get_by_text("Read original context",exact=True).first.click()
        page.get_by_text("Characters ",exact=False).first.wait_for()
        page.get_by_text("Characters ",exact=False).first.scroll_into_view_if_needed()
        slide("Inspecting the original document","The character offsets resolve directly into the stored document; adjacent words preserve the relation.",7,"evidence.png")
        if args.predictions:
            import sys
            sys.path.insert(0,str(ROOT/"code"))
            from searchkit.runs import validate
            rows=[json.loads(line) for line in args.predictions.read_text(encoding="utf-8").splitlines() if line]
            cases={}
            for r in rows:
                validate(r,r["id"],r["question"])
                for s in r["trajectory"]:
                    if s.get("role")=="tool" and s["name"]=="load_skill":
                        name=json.loads(s["content"]).get("name")
                        if name and name not in cases: cases[name]=r
            chosen=list({r["id"]:r for r in cases.values()}.values())[:2] or rows[:1]
            for case in chosen:
                page.get_by_text("Replay a run",exact=True).click()
                page.locator('input[type="file"]').set_input_files({"name":"observed.jsonl","mimeType":"application/json","buffer":(json.dumps(case)+"\n").encode()})
                page.get_by_role("heading",name="Tool timeline").wait_for()
                slide("Recorded DeepSeek run | question "+case["id"],"Replay displays the actual final answer, API usage, selected skills and source evidence.",9,"agent.png")
                action=page.get_by_text("→ search",exact=True).last
                action.click();action.scroll_into_view_if_needed()
                slide("Result-dependent action","This search argument comes from a recorded model tool call. Complete messages are included in the JSONL.",8)
        else:
            page.get_by_text("Ask an agent",exact=True).click()
            page.get_by_role("textbox",name="Question").fill("Which source passage identifies the person described by these clues?")
            slide("Retrieval demonstration | agent run pending","A course-model API key is required for live answers, skill selection and token accounting.",6)
        page.set_content("""<style>body{background:#f5f7f7;color:#143044;font:24px Segoe UI, sans-serif;padding:56px}h1{font-size:45px}dt{font: bold 27px Consolas;color:#156A68;margin-top:25px}dd{margin:6px 0 0}p{color:#527078}</style>
        <p>COMP5423 / IMPLEMENTATION</p><h1>How the project is organized</h1><dl>
        <dt>store.py · dense.py · retrieval.py</dt><dd>Document storage, neural indexes, ranked fusion and source windows.</dd>
        <dt>agent.py · provider.py · skills/</dt><dd>Model decisions, evidence state, context selection and runtime skill loading.</dd>
        <dt>runs.py · main.py</dt><dd>Question checkpoints, trace validation, batch generation and normalized exact match.</dd>
        <dt>app.py</dt><dd>Interactive search, original context and chronological replay of submitted records.</dd></dl>""")
        slide("Code structure","All submission metrics come from the provider response and tool dispatcher for each question.",7)
        br.close()
        listing=work/"frames.txt"
        lines=[]
        for file,seconds in slides:lines.extend(["file '"+file.name+"'","duration "+str(seconds)])
        lines.append("file '"+slides[-1][0].name+"'");listing.write_text("\n".join(lines),encoding="ascii")
        subprocess.run([args.ffmpeg,"-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(listing),"-vf","fps=12,format=yuv420p","-c:v","libx264","-preset","veryfast","-movflags","+faststart",str(args.output)],cwd=work,check=True)
        print("Video:",args.output,"duration ~",sum(n for _,n in slides),"seconds")
if __name__=="__main__":main()
