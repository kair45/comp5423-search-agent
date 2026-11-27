"""Offline regression tests. Synthetic tool messages never enter submission outputs."""
import json
from pathlib import Path
import tempfile
import unittest

from searchkit.agent import Agent
from searchkit.runs import SKILLS, validate, normalized, atomic_text
from searchkit.retrieval import Retrieval
from searchkit.store import build_store

class CourseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        rows=[{"docid":"17","url":"https://example.org/a","text":"The Cobalt Guild built Test Observatory. It installed the quartz telescope."},
              {"docid":"42","url":"https://example.org/b","text":"Ada Grey designed the quartz telescope. Another instrument was made by Lee."}]
        f=self.root/"corpus.jsonl";atomic_text(f,"".join(json.dumps(r)+"\n" for r in rows))
        build_store(f,self.root/"index/documents.sqlite",2)
        self.engine=Retrieval(self.root,["bm25"])
        self.addCleanup(self.engine.store.con.close)
    def test_offsets_and_missing_id(self):
        hit=self.engine.search("quartz telescope")[0]
        for p in hit["passages"]:
            text,_=self.engine.store.get(hit["doc_id"]);self.assertEqual(p["quote"],text[p["start"]:p["end"]])
        with self.assertRaises(KeyError): self.engine.store.read("bad")
        self.assertEqual(normalized("The A.D.A!"),"ada")
    def test_resumed_run_is_paired_and_counted(self):
        actions=[("load_skill",{"name":"follow-clues"}),("search",{"query":"Cobalt Guild"}),("read_document",{"doc_id":"17"}),
                 ("search",{"query":"quartz telescope designer","candidate":"quartz","unresolved":["designer"]}),
                 ("read_document",{"doc_id":"42"}),"Ada Grey"]
        class TestProvider:
            model="unit-test"
            def __init__(self): self.i=0
            def complete(self,messages,tools,choice):
                action=actions[self.i]; self.i+=1
                msg={"role":"assistant","content":None}
                if isinstance(action,str): msg["content"]=action
                else:
                    name,args=action;msg["tool_calls"]=[{"id":"t"+str(self.i),"type":"function","function":{"name":name,"arguments":json.dumps(args)}}]
                return msg,{"total_tokens":self.i},{"model":self.model}
        p=TestProvider();agent=Agent(self.engine,p,SKILLS,budget=8); saved=[]
        def interrupt(state):
            saved[:]=[json.loads(json.dumps(state))]
            if state["pending"] and p.i==2: raise InterruptedError()
        with self.assertRaises(InterruptedError):agent.run("q","Who designed the instrument?",save=interrupt)
        row=agent.run("q","Who designed the instrument?",saved[0])
        validate(row,"q",row["question"])
        self.assertEqual((row["total_tokens"],row["tool_calls"],p.i),(21,5,6))
        self.assertTrue(any(s.get("event")=="context" for s in row["trajectory"]))
        row["tool_calls"]=0
        with self.assertRaises(ValueError): validate(row,"q",row["question"])
    def test_formatting_resumes_without_repeating_provider_work(self):
        draft="The requested answer is **Ada Grey**.\\n\\nThe document names the designer."
        search={"id":"once","type":"function","function":{"name":"search","arguments":json.dumps({"query":"designer"})}}
        class FormattingProvider:
            def __init__(self):
                self.responses=iter([{"role":"assistant","tool_calls":[search]}, {"role":"assistant","content":draft},
                                     {"role":"assistant","content":"Ada Grey"}])
                self.requests=[]
            def complete(self,messages,tools,choice):
                self.requests.append((messages,tools))
                return next(self.responses),{"total_tokens":7},{"model":"unit-test"}
        provider=FormattingProvider()
        agent=Agent(self.engine,provider,SKILLS,profile="A")
        checkpoint=[]
        def interrupt(state):
            if state.get("format_draft") and state["answer"] is None:
                checkpoint.append(json.loads(json.dumps(state)))
                raise InterruptedError()
        question="Who designed the instrument?"
        with self.assertRaises(InterruptedError): agent.run("q",question,save=interrupt)
        row=agent.run("q",question,checkpoint[0])
        validate(row,"q",question)
        self.assertEqual((row["answer"],row["tool_calls"],row["total_tokens"]),("Ada Grey",1,21))
        self.assertEqual(provider.requests[-1][1],[])
        self.assertEqual(json.loads(provider.requests[-1][0][-1]["content"])["draft"],draft)

    def test_truncated_tool_fragment_is_counted_and_never_executed(self):
        fragment={"id":"cut","type":"function","function":{"name":"search","arguments":"{"}}
        complete={"id":"done","type":"function","function":{"name":"search","arguments":json.dumps({"query":"designer"})}}
        class TruncatedProvider:
            def __init__(self):
                self.messages=iter([({"tool_calls":[fragment]},"length"),({"tool_calls":[complete]},"tool_calls"),({"content":"Ada Grey"},"stop")])
            def complete(self,messages,tools,choice):
                for item in messages:
                    self_tools=item.get("tool_calls") or []
                    if any(c["id"]=="cut" for c in self_tools): raise AssertionError("Replayed an incomplete call")
                msg,reason=next(self.messages)
                return {"role":"assistant",**msg},{"total_tokens":7},{"finish_reason":reason}
        for profile in ("A","E"):
            agent=Agent(self.engine,TruncatedProvider(),SKILLS,profile=profile,budget=1)
            row=agent.run("q","Who designed the instrument?")
            validate(row,"q",row["question"])
            self.assertEqual((row["tool_calls"],row["total_tokens"],row["answer"]),(1,21,"Ada Grey"))

    def test_catalog_and_conflict_skill(self):
        agent=Agent(self.engine,None,SKILLS)
        mem=agent.initial("q","q")["memory"]
        self.assertIn("unknown",agent.execute("load_skill",{"name":"resolve-entity"},mem)["instructions"])
        with self.assertRaises(ValueError): agent.execute("load_skill",{"name":"../x"},mem)
        with self.assertRaises(ValueError): agent.execute("read_document",{"doc_id":"17"},mem)
if __name__=="__main__": unittest.main()
