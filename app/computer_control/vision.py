from __future__ import annotations
import base64,json,urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

@dataclass(frozen=True)
class VisionRequest:
    image_path:Path; prompt:str; max_output_tokens:int=512
    def validate(self):
        if not self.prompt.strip(): raise ValueError("prompt must be non-empty")
        if self.max_output_tokens<=0: raise ValueError("max_output_tokens must be > 0")
        if not self.image_path.is_file(): raise FileNotFoundError(self.image_path)

@dataclass(frozen=True)
class VisionElement:
    label:str; confidence:float; x:int; y:int; width:int; height:int
    text:str|None=None; role:str|None=None
    def validate(self):
        if not self.label.strip() or not 0<=self.confidence<=1 or min(self.x,self.y)<0 or self.width<=0 or self.height<=0: raise ValueError("invalid vision element")

@dataclass(frozen=True)
class VisionObservation:
    provider:str; model:str; width:int; height:int; elements:tuple[VisionElement,...]=(); raw_text:str|None=None
    def validate(self):
        if self.width<=0 or self.height<=0: raise ValueError("invalid observation dimensions")
        for e in self.elements:
            e.validate()
            if e.x+e.width>self.width or e.y+e.height>self.height: raise ValueError("vision element outside image")

class VisionProvider(Protocol):
    name:str; model:str
    def observe(self,request:VisionRequest)->VisionObservation: ...

class JsonVisionProvider:
    def __init__(self,*,name,model): self.name=name; self.model=model
    def parse(self,payload,*,width,height):
        data=json.loads(payload); items=[]
        for i in data.get("elements",[]):
            e=VisionElement(str(i["label"]),float(i["confidence"]),int(i["x"]),int(i["y"]),int(i["width"]),int(i["height"]),i.get("text"),i.get("role"))
            e.validate(); items.append(e)
        o=VisionObservation(self.name,self.model,width,height,tuple(items),data.get("text")); o.validate(); return o

class OllamaVisionProvider(JsonVisionProvider):
    def __init__(self,*,model="qwen3-vl:8b",base_url="http://127.0.0.1:11434",timeout_seconds=60.0):
        super().__init__(name="ollama",model=model); self.base_url=base_url.rstrip("/"); self.timeout_seconds=timeout_seconds
    def observe(self,request):
        request.validate(); raw=base64.b64encode(request.image_path.read_bytes()).decode("ascii")
        prompt=request.prompt+' Return ONLY JSON with keys text and elements. Each element must have label, confidence, x, y, width, height, optional text and role.'
        body=json.dumps({"model":self.model,"prompt":prompt,"images":[raw],"stream":False,"format":"json","options":{"num_predict":request.max_output_tokens}}).encode()
        req=urllib.request.Request(self.base_url+"/api/generate",data=body,headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=self.timeout_seconds) as response: data=json.loads(response.read().decode())
        if "response" not in data: raise RuntimeError("Ollama response missing response")
        try:
            from PIL import Image
            with Image.open(request.image_path) as im: w,h=im.size
        except Exception as exc: raise RuntimeError("Pillow is required for vision image dimensions") from exc
        return self.parse(data["response"],width=w,height=h)
