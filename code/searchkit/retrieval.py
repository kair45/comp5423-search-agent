from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .store import Store, locate

class Retrieval:
    def __init__(self,data,methods=("bm25","e5","qwen")):
        self.data=Path(data); self.store=Store(self.data/"index"); self.methods=tuple(methods)
        if not self.methods or set(self.methods)-{"bm25","e5","qwen"}: raise ValueError("Unknown retrieval method")
        self.dense={}
    def search(self, query, intent="", top=5, depth=30):
        if not isinstance(query,str) or not query.strip(): raise ValueError("Supply a nonempty search query")
        if not (1<=top<=depth<=100): raise ValueError("Expected 1 <= top <= depth <= 100")
        return self._rank(query.strip(),intent.strip(),top,depth)
    @lru_cache(maxsize=128)
    def _rank(self,query,intent,top,depth):
        ranks=defaultdict(dict); score=defaultdict(float); anchors={}
        for method in self.methods:
            if method=="bm25":
                hits=[(docid,value,None) for docid,value in self.store.sparse(query,depth)]
            else:
                if method not in self.dense:
                    from .dense import Dense
                    self.dense[method]=Dense(self.data,method,self.store.corpus_id)
                hits=self.dense[method].search(query,depth,intent)
            for rank,(docid,raw,span) in enumerate(hits,1):
                ranks[docid][method]={"rank":rank,"score":round(float(raw),6)}
                score[docid]+=1/(60+rank)
                if span and span[1]>span[0]: anchors[docid]=span
        results=[]
        for docid in sorted(score,key=lambda k:(-score[k],k))[:top]:
            text,url=self.store.get(docid); fragments=locate(text,query,1)
            span=anchors.get(docid)
            if span and (not fragments or span[1]<=fragments[0]["start"] or span[0]>=fragments[0]["end"]):
                l,r=span; fragments.append({"start":l,"end":r,"quote":text[l:r]})
            results.append({"doc_id":docid,"score":round(score[docid],7),"url":url,"snippet":fragments[0]["quote"] if fragments else "","passages":fragments,"ranks":ranks[docid]})
        return results
