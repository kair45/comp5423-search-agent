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
    def test_catalog_and_conflict_skill(self):
        agent=Agent(self.engine,None,SKILLS)
        mem=agent.initial("q","q")["memory"]
        self.assertIn("unknown",agent.execute("load_skill",{"name":"resolve-entity"},mem)["instructions"])
        with self.assertRaises(ValueError): agent.execute("load_skill",{"name":"../x"},mem)
        with self.assertRaises(ValueError): agent.execute("read_document",{"doc_id":"17"},mem)
if __name__=="__main__": unittest.main()
