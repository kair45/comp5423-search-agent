"""Streamlit UI using the same retrieval and agent entry points as batch generation."""
import json
from pathlib import Path
from threading import RLock

import streamlit as st

from searchkit.agent import Agent, CONFIGS
from searchkit.provider import Provider, ROOT
from searchkit.retrieval import Retrieval
from searchkit.runs import SKILLS

st.set_page_config(page_title="Evidence Search · COMP5423",layout="wide")
st.title("Evidence Search")
choice=st.sidebar.radio("Workspace",["Ask an agent","Explore the collection","Replay a run"])
data=ROOT/"data"

@st.cache_resource
def engines(profile):
    return Retrieval(data,CONFIGS[profile][0]),RLock()

def show_record(row):
    st.subheader("Answer")
    st.write(row["answer"])
    a,b=st.columns(2);a.metric("Tool calls",row["tool_calls"]);b.metric("API tokens",row["total_tokens"])
    trace=row["trajectory"]; selected=[]; read=[];snippets=[]
    for step in trace:
        if step.get("role")!="tool": continue
        result=json.loads(step["content"])
        if step["name"]=="load_skill" and "name" in result: selected.append(result["name"])
        if step["name"]=="read_document" and "quote" in result: read.append(result)
        if step["name"]=="search":
            for hit in result.get("results",[]):
                for segment in hit.get("passages",[]): snippets.append((hit["doc_id"],segment["snippet"]))
    st.write("Selected skills",", ".join(dict.fromkeys(selected)) or "None")
    left,right=st.columns([1,1])
    with left:
        st.subheader("Source evidence")
        for r in read:
            st.caption(f"Document {r['doc_id']} · characters {r['start']}–{r['end']}")
            st.text(r["quote"])
            if r.get("url"): st.write(r["url"])
        if not read:
            for docid,text in snippets[:5]: st.caption("Search result · "+docid);st.text(text)
    with right:
        st.subheader("Tool timeline")
        for step in trace:
            if step.get("event")=="context":
                with st.expander("Working state"): st.json(step["state"])
            if step.get("api",{}).get("finish_reason")=="length":
                st.caption("Incomplete model reply; its token usage is included.")
                continue
            for call in step.get("tool_calls") or []:
                with st.expander("→ "+call["function"]["name"]): st.code(call["function"]["arguments"],language="json")
            if step.get("role")=="tool":
                with st.expander("← "+step["name"]): st.json(json.loads(step["content"]))

if choice=="Ask an agent":
    st.caption("Ask a question about the fixed BrowseComp-Plus collection.")
    with st.form("ask"):
        q=st.text_area("Question",height=100); go=st.form_submit_button("Search and answer",type="primary")
    if go and q.strip():
        try:
            provider=Provider()
            with st.status("Searching the collection",expanded=True) as status:
                r,lock=engines("F")
                with lock:
                    row=Agent(r,provider,SKILLS,profile="F").run("interactive",q,notify=lambda name,result:st.write(name))
                st.session_state["answer"]=row; status.update(label="Answer ready",state="complete",expanded=False)
        except (ValueError,RuntimeError,OSError) as e: st.error(str(e))
    if "answer" in st.session_state: show_record(st.session_state["answer"])
elif choice=="Explore the collection":
    st.caption("Search the fixed corpus and inspect the original passage.")
    with st.form("explore"):
        query=st.text_input("Search query")
        go=st.form_submit_button("Find evidence",type="primary")
    if go and query.strip():
        r,lock=engines("E")
        with st.spinner("Retrieving ranked documents"),lock:
            st.session_state["hits"]=r.search(query)
    for hit in st.session_state.get("hits",[]):
        st.subheader("Document "+hit["doc_id"])
        st.caption("RRF {:.5f}  ·  ".format(hit["score"])+"  ·  ".join(name+" #"+str(data["rank"]) for name,data in hit["ranks"].items()))
        st.write(hit["snippet"]); st.caption(hit["url"])
        with st.expander("Read original context"):
            r,lock=engines("E")
            with lock:
                item=r.store.read(hit["doc_id"],start=hit["passages"][0]["start"])
            st.text(item["quote"]);st.caption(f"Characters {item['start']}–{item['end']}")
else:
    file=st.file_uploader("Open a prediction JSONL",type=["jsonl","json"])
    if file:
        try:
            rows=[json.loads(x) for x in file.getvalue().decode("utf-8-sig").splitlines() if x.strip()]
            i=st.selectbox("Question",range(len(rows)),format_func=lambda i:rows[i]["id"]+" · "+rows[i]["question"][:70])
            st.write(rows[i]["question"]);show_record(rows[i])
        except (ValueError,KeyError,IndexError) as e: st.error("Cannot read this prediction file: "+str(e))
