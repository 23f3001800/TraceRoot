"""Loopback HTTP and WebSocket approval API."""
from __future__ import annotations
import asyncio, json, threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from websockets.asyncio.server import serve
from ..agents.approval import ApprovalRecord, patch_hash, save_approval
class ApprovalAPI:
 def __init__(self,context,patch_path,investigation_id):
  self.context=context;self.patch=Path(patch_path).read_bytes().decode("utf-8");self.investigation_id=investigation_id;self.digest=patch_hash(self.patch);self.clients=set()
 def payload(self): return {"type":"approval_context","investigation":self.investigation_id,"repository":self.context.repository.source,"session":self.context.config["id"],"hash":self.digest,"patch":self.patch}
 async def websocket(self,ws):
  self.clients.add(ws);await ws.send(json.dumps(self.payload()))
  try:
   async for _ in ws: pass
  finally:self.clients.discard(ws)
 def approve(self,person):
  approval_id="a"+datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f");record=ApprovalRecord(approval_id,self.investigation_id,self.digest,self.context.repository.source,self.context.config["id"],person,datetime.now(timezone.utc).isoformat(),(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat());save_approval(self.context,record);return {"type":"approval_created","message":"Exact patch approved.","approval_id":approval_id}
 def handler(self,ui_root):
  api=self
  class Handler(BaseHTTPRequestHandler):
   def reply(self,status,data,kind):self.send_response(status);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
   def do_GET(self):
    if self.path=="/api/approval-context":return self.reply(200,json.dumps(api.payload()).encode(),"application/json")
    name="index.html" if self.path=="/" else self.path.removeprefix("/ui/") if self.path.startswith("/ui/") else "";file=(ui_root/name).resolve()
    if ui_root not in file.parents or not file.is_file():return self.reply(404,b"Not found","text/plain")
    self.reply(200,file.read_bytes(),"text/css" if file.suffix==".css" else "application/javascript" if file.suffix==".js" else "text/html; charset=utf-8")
   def do_POST(self):
    if self.path!="/api/approve":return self.reply(404,b"{}","application/json")
    person=(parse_qs(self.rfile.read(min(int(self.headers.get("Content-Length","0")),4096)).decode()).get("approved_by")or[""])[0].strip()
    if not person or len(person)>80:return self.reply(400,b'{"message":"Invalid approver."}',"application/json")
    self.reply(200,json.dumps(api.approve(person)).encode(),"application/json")
   def log_message(self,*args):pass
  return Handler
def serve_approval(context,patch_path,investigation_id,port=8765):
 api=ApprovalAPI(context,patch_path,investigation_id);ui_root=Path(__file__).parents[2]/"ui";http=ThreadingHTTPServer(("127.0.0.1",port),api.handler(ui_root));threading.Thread(target=http.serve_forever,daemon=True).start()
 async def run():
  async with serve(api.websocket,"127.0.0.1",port+1):await asyncio.Future()
 print("TraceRoot UI: http://127.0.0.1:"+str(port)+" WebSocket: ws://127.0.0.1:"+str(port+1),flush=True);asyncio.run(run())
