"""Read-only document store and atomic construction of the BM25 corpus index."""
import collections
import hashlib
import heapq
import itertools
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import zlib

WORDS = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)
STOP = set("a an the of and or to for from by who what which when where why how as at in on did their was were is are has had with that this these those it his her its she he they person entity document passages find identify between".split())

def terms(text):
    return list(dict.fromkeys(w.casefold() for w in WORDS.findall(text) if w.casefold() not in STOP))[:64]

def corpus_rows(path):
    paths = sorted(path.glob("*.parquet")) if path.is_dir() else [path]
    if not paths:
        raise ValueError(f"No corpus shards in {path}")
    for shard in paths:
        if shard.suffix == ".parquet":
            import pyarrow.parquet as pq
            for batch in pq.ParquetFile(shard).iter_batches(batch_size=96, columns=["docid", "text", "url"]):
                yield from batch.to_pylist()
        else:
            with shard.open(encoding="utf-8-sig") as file:
                yield from (json.loads(line) for line in file if line.strip())

def windows(text, size=230, overlap=38):
    """Return exact character spans. Keep whitespace offsets for source verification."""
    matches = list(re.finditer(r"\S+", text))
    if not matches:
        return
    for start in range(0,len(matches),size-overlap):
        last = min(start+size,len(matches))
        yield matches[start].start(), matches[last-1].end()
        if last == len(matches):
            break

def locate(text, query, count=2, size=95):
    keys=set(terms(query))
    best=[]
    for start,end in windows(text,size,min(18,size//4)):
        words=collections.Counter(w.casefold() for w in WORDS.findall(text[start:end]))
        score=sum((1+min(len(word),12)/12)*math.log1p(words[word]) for word in keys if word in words)
        heapq.heappush(best,(score,-start,end))
        if len(best)>count:
            heapq.heappop(best)
    return [{"start":-neg,"end":end,"quote":text[-neg:end]} for _,neg,end in sorted(best,reverse=True)]

def connect(path, readonly=False):
    uri=path.resolve().as_uri()+"?mode=ro" if readonly else str(path)
    return sqlite3.connect(uri, uri=readonly, timeout=30, check_same_thread=not readonly)

def build_store(source, out, expected=None):
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        raise FileExistsError(f"Choose a new index directory: {out}")
    staged=out.with_name(out.name+".building")
    con=connect(staged)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
          CREATE TABLE IF NOT EXISTS docs (n INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, url TEXT NOT NULL, body BLOB NOT NULL);
          CREATE VIRTUAL TABLE IF NOT EXISTS lexical USING fts5(body, content='', tokenize='unicode61');
          CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        paths=sorted(source.glob("*.parquet")) if source.is_dir() else [source]
        stamp=json.dumps([(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in paths])
        old=con.execute("SELECT value FROM meta WHERE key='source'").fetchone()
        if old and old[0]!=stamp:
            raise ValueError("The source changed since the interrupted build. Choose a fresh index directory.")
        con.execute("INSERT OR IGNORE INTO meta VALUES ('source',?)",(stamp,))
        con.commit()
        done=con.execute("SELECT count(*) FROM docs").fetchone()[0]
        rows=itertools.islice(corpus_rows(source),done,None)
        for n,row in enumerate(rows,done+1):
            docid=row.get("docid",row.get("doc_id"))
            if docid is None or not isinstance(row["text"],str):
                raise ValueError("Corpus requires docid and text")
            text=row["text"]
            con.execute("INSERT INTO docs VALUES (?,?,?,?)",(n,str(docid),row.get("url",""),zlib.compress(text.encode(),1)))
            con.execute("INSERT INTO lexical(rowid,body) VALUES (?,?)",(n,text))
            if n%500==0:
                con.commit()
                if n%5000==0: print("BM25 documents",n,flush=True)
        total=con.execute("SELECT count(*) FROM docs").fetchone()[0]
        if not total or (expected is not None and total!=expected):
            raise ValueError(f"Found {total} documents; expected {expected}")
        digest=hashlib.sha256()
        for docid, in con.execute("SELECT id FROM docs ORDER BY n"):
            digest.update(docid.encode()+b"\n")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('corpus_id',?)",(digest.hexdigest(),))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
    finally:
        con.close()
    os.replace(staged,out)
    print("BM25 ready:",total,"documents",flush=True)

class Store:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.con=connect(self.directory/"documents.sqlite",readonly=True)
        self.corpus_id=self.con.execute("SELECT value FROM meta WHERE key='corpus_id'").fetchone()[0]
    def get(self,docid):
        row=self.con.execute("SELECT body,url FROM docs WHERE id=?",(str(docid),)).fetchone()
        if row is None: raise KeyError("Unknown document ID")
        return zlib.decompress(row[0]).decode(),row[1]
    def sparse(self,query,limit=30):
        tokens=terms(query) or WORDS.findall(query)[:8]
        if not tokens: return []
        expr=" OR ".join('"'+t.replace('"','""')+'"' for t in tokens)
        return [(docid,-score) for docid,score in self.con.execute(
            "SELECT d.id,rank FROM lexical JOIN docs d ON d.n=lexical.rowid WHERE lexical MATCH ? ORDER BY rank LIMIT ?",(expr,limit))]
    def read(self,doc_id,focus="",start=None):
        text,url=self.get(doc_id)
        if start is None:
            hit=locate(text,focus,1) if focus else []
            start=hit[0]["start"] if hit else 0
        if not isinstance(start,int) or not 0<=start<=len(text):
            raise ValueError("start must be a character offset in the document")
        left=max(0,start-260); right=min(len(text),start+1250)
        return {"doc_id":str(doc_id),"url":url,"start":left,"end":right,"quote":text[left:right],"length":len(text)}
