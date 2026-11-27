"""Course-model chat completions on SiliconFlow or Alibaba Cloud Model Studio."""
import os
from pathlib import Path
import re
import time
import requests

ROOT=Path(__file__).resolve().parents[2]

def settings():
    values={}
    path=ROOT/".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k,sep,v=line.partition("="); values[k.strip()]=v.strip().strip("'\"")
    def env(name,default=""): return os.environ.get(name) or values.get(name) or default
    service=env("LLM_PROVIDER","siliconflow").lower()
    if service=="siliconflow":
        return env("SILICONFLOW_API_KEY"),"https://api.siliconflow.cn/v1","deepseek-ai/DeepSeek-V4-Flash"
    if service!="aliyun": raise ValueError("LLM_PROVIDER must be siliconflow or aliyun.")
    workspace=env("DASHSCOPE_WORKSPACE_ID"); region=env("DASHSCOPE_REGION","cn-beijing")
    if not re.fullmatch(r"[a-zA-Z0-9-]+",workspace) or not re.fullmatch(r"[a-z0-9-]+",region):
        raise ValueError("Set your Alibaba Cloud workspace ID and region in .env.")
    return env("DASHSCOPE_API_KEY"),f"https://{workspace}.{region}.maas.aliyuncs.com/compatible-mode/v1","deepseek-v4-flash-0731"

class Provider:
    def __init__(self):
        self.key,self.base,self.model=settings()
        if not self.key:
            name="SILICONFLOW_API_KEY" if self.model.startswith("deepseek-ai/") else "DASHSCOPE_API_KEY"
            raise ValueError(f"Fill {name} in the project .env to enable agent answers.")
        self.http=requests.Session()
    def complete(self,messages,tools,choice=None):
        payload={"model":self.model,"messages":messages,"max_tokens":3072,"temperature":0,"enable_thinking":False}
        if tools:
            payload["tools"]=tools
            if choice: payload["tool_choice"]=choice
        for attempt in range(4):
            try:
                response=self.http.post(self.base+"/chat/completions",json=payload,
                    headers={"Authorization":"Bearer "+self.key},timeout=(15,150),allow_redirects=False)
            except requests.RequestException as e:
                raise RuntimeError(f"LLM connection failed ({type(e).__name__}); no prediction emitted.") from None
            if response.status_code!=429 or attempt==3: break
            try: delay=float(response.headers.get("Retry-After","2"))
            except ValueError: delay=2
            time.sleep(min(30,max(1,delay)*(attempt+1)))
        if not response.ok or response.is_redirect:
            raise RuntimeError(f"LLM service returned HTTP {response.status_code}. Check the key, model access, region or quota.")
        body=response.json(); usage=body.get("usage",{})
        returned=str(body.get("model","")).lower()
        if returned not in {self.model.lower(),"deepseek-v4-flash-0731","deepseek-ai/deepseek-v4-flash-0731","deepseek-v4-flash","deepseek-ai/deepseek-v4-flash"}:
            raise ValueError("Provider did not confirm the requested DeepSeek-V4-Flash model.")
        if type(usage.get("total_tokens")) is not int or usage["total_tokens"]<0:
            raise ValueError("Missing provider-reported usage.total_tokens; the run cannot be scored.")
        result=body["choices"][0]
        if result.get("finish_reason") not in ("stop","tool_calls","length"):
            raise ValueError("Incomplete LLM response: "+str(result.get("finish_reason")))
        return result["message"],usage,{"model":body.get("model"),"response_id":body.get("id"),"finish_reason":result.get("finish_reason")}
