"""Build/search two real embedding indexes, with ID-aligned, resumable E5 shards."""
import hashlib
import json
import os
from pathlib import Path
import pickle
import re

import faiss
import numpy as np

from .store import corpus_rows, windows

class Encoder:
    def __init__(self, path, family, device=None):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch=torch
        self.device=device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.family=family
        self.tokenizer=AutoTokenizer.from_pretrained(str(path),local_files_only=True)
        if family=="qwen": self.tokenizer.padding_side="left"
        dtype=torch.float16 if self.device=="cuda" else torch.float32
        self.model=AutoModel.from_pretrained(str(path),local_files_only=True,torch_dtype=dtype).to(self.device).eval()
    def encode(self, texts, query=False, intent=""):
        torch=self.torch
        if self.family=="e5":
            prefix="query: " if query else "passage: "
            texts=[prefix+t for t in texts]
        elif query:
            instruction=intent or "Given a web search query, retrieve relevant passages that answer the query"
            texts=["Instruct: "+instruction+"\nQuery: "+t for t in texts]
        batch=self.tokenizer(texts,padding=True,truncation=True,max_length=320 if self.family=="e5" else 512,return_tensors="pt").to(self.device)
        with torch.inference_mode():
            hidden=self.model(**batch).last_hidden_state
            if self.family=="e5":
                mask=batch["attention_mask"].unsqueeze(-1)
                pooled=(hidden*mask).sum(1)/mask.sum(1).clamp(min=1)
            else:
                pooled=hidden[:,-1]
            vectors=torch.nn.functional.normalize(pooled.float(),dim=-1)
        return np.ascontiguousarray(vectors.cpu().numpy(),dtype=np.float32)

def anchors(text, limit):
    if limit==0:
        yield from windows(text)
        return
    if not text.strip(): yield (0,0); return
    for i in range(limit):
        if i and len(text)<850*limit: break
        start=i*len(text)//limit
        if start:
            hit=re.search(r"\s",text[start:start+40]); start+=hit.end() if hit else 0
        yield start,min(len(text),start+640)

def make_e5(data, source, limit=2, batch_size=32):
    data=Path(data); target=data/"index"; target.mkdir(exist_ok=True,parents=True)
    encoder=Encoder(data/"models/e5","e5")
    model_hash=hashlib.sha256((data/"models/e5/config.json").read_bytes()).hexdigest()
    files=sorted(source.glob("*.parquet")) if source.is_dir() else [source]
    stamp=hashlib.sha256(json.dumps([(p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in files]).encode()).hexdigest()[:12]
    work=target/f"e5-parts-{limit}-{stamp}-{model_hash[:8]}"; work.mkdir(exist_ok=True)
    groups=[]; rows=[]; texts=[]; ids=[]; spans=[]; vectors=[]; docs=0
    def flush_batch():
        if texts:
            vectors.append(encoder.encode(texts))
            texts.clear()
    def save_shard(number):
        flush_batch()
        file=work/f"{number:05}.npz"; part=file.with_suffix(".partial")
        with part.open("wb") as stream:
            np.savez(stream,v=np.concatenate(vectors).astype(np.float16),ids=np.array(ids),spans=np.array(spans,dtype=np.int32))
        os.replace(part,file)
        texts.clear(); ids.clear(); spans.clear(); vectors.clear()
    for row in corpus_rows(source):
        docid=str(row.get("docid",row.get("doc_id")))
        text=row["text"]; number=docs//512
        chunk=work/f"{number:05}.npz"
        if docs%512==0:
            groups.append(chunk); cached=chunk.exists()
        docs+=1
        if not cached:
            for left,right in anchors(text,limit):
                ids.append(docid); spans.append((left,right)); texts.append(text[left:right])
                if len(texts)>=batch_size: flush_batch()
            if docs%512==0: save_shard(number)
        if docs%5120==0: print("E5 documents",docs,flush=True)
        rows.append(docid)
    if texts or vectors: save_shard((docs-1)//512)
    if not rows: raise ValueError("No documents")
    index=faiss.IndexFlatIP(384); allids=[]; allspans=[]
    for group in groups:
        with np.load(group,allow_pickle=False) as part:
            values=part["v"].astype(np.float32); faiss.normalize_L2(values); index.add(values)
            allids.extend(part["ids"].tolist()); allspans.append(part["spans"])
    publish(target,"e5",index,allids,np.concatenate(allspans),rows)
    print("E5 ready",docs,index.ntotal,flush=True)

class ArraysOnly(pickle.Unpickler):
    def find_class(self,module,name):
        if (module,name) in {("numpy.core.multiarray","_reconstruct"),("numpy","ndarray"),("numpy","dtype")}:
            return super().find_class(module,name)
        raise ValueError("Unsupported object in published embedding shard")

def publish(path,family,index,ids,spans,corpus):
    import uuid
    revision=uuid.uuid4().hex
    base=path/(family+"-"+revision)
    faiss.write_index(index,str(base)+".faiss")
    np.savez(str(base)+".npz",ids=np.asarray(ids,dtype=str),spans=spans)
    digest=hashlib.sha256()
    for docid in corpus: digest.update((docid+"\n").encode())
    meta={"base":base.name,"vectors":index.ntotal,"corpus_id":digest.hexdigest()}
    tmp=path/(family+".json."+revision)
    tmp.write_text(json.dumps(meta),encoding="utf-8"); os.replace(tmp,path/(family+".json"))

def import_qwen(data,source):
    data=Path(data); dest=data/"index"; dest.mkdir(exist_ok=True,parents=True)
    ids=[]; index=faiss.IndexFlatIP(1024)
    files=sorted((data/"qwen-index").glob("corpus.shard*_of_*.pkl"))
    if not files: raise ValueError("Public Qwen embedding shards are missing")
    manifest=json.loads((data/"public-manifest.json").read_text(encoding="utf-8-sig"))
    for file in files:
        digest=next((r["sha256"] for r in manifest if r["url"].endswith("/"+file.name)),None)
        if not digest or hashlib.sha256(file.read_bytes()).hexdigest()!=digest: raise ValueError("Unverified shard: "+file.name)
        with file.open("rb") as handle: values,labels=ArraysOnly(handle).load()
        values=np.ascontiguousarray(values,dtype=np.float32)
        if len(values)!=len(labels) or values.shape[1]!=1024: raise ValueError("Invalid Qwen embedding dimensions")
        faiss.normalize_L2(values); index.add(values); ids.extend(str(x) for x in labels)
    if source.is_dir():
        import pyarrow.parquet as pq
        ordered=[str(x) for f in sorted(source.glob("*.parquet")) for b in pq.ParquetFile(f).iter_batches(columns=["docid"]) for x in b.column(0).to_pylist()]
    else: ordered=[str(r.get("docid",r.get("doc_id"))) for r in corpus_rows(source)]
    if len(ids)!=len(set(ids)) or set(ids)!=set(ordered): raise ValueError("Public index IDs do not match corpus")
    publish(dest,"qwen",index,ids,np.zeros((len(ids),2),np.int32),ordered)
    print("Qwen ready",len(ordered),"documents",flush=True)

class Dense:
    def __init__(self,data,family,corpus_id):
        root=Path(data)/"index"
        meta=json.loads((root/(family+".json")).read_text(encoding="utf-8"))
        if meta["corpus_id"]!=corpus_id: raise ValueError("Dense and lexical corpus IDs differ")
        base=root/meta["base"]
        self.index=faiss.read_index(str(base)+".faiss")
        with np.load(str(base)+".npz",allow_pickle=False) as aux: self.ids=aux["ids"]; self.spans=aux["spans"]
        if self.index.ntotal!=len(self.ids): raise ValueError("Index metadata mismatch")
        self.encoder=Encoder(Path(data)/"models"/family,family)
    def search(self,query,limit,intent=""):
        vec=self.encoder.encode([query],query=True,intent=intent)
        k=min(self.index.ntotal,max(2*limit,limit))
        while k:
            scores,indices=self.index.search(vec,k); hits={}
            for i,score in zip(indices[0],scores[0]):
                if i<0: continue
                docid=str(self.ids[i])
                if docid not in hits: hits[docid]=(float(score),self.spans[i].tolist())
                if len(hits)==limit: break
            if len(hits)>=limit or k==self.index.ntotal: break
            k=min(2*k,self.index.ntotal)
        return [(docid,*v) for docid,v in hits.items()]
