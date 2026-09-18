"""Loopback-only incident reporting workspace with durable local reports."""
from __future__ import annotations
import asyncio, json, threading
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
from urllib.parse import parse_qs
from websockets.asyncio.server import serve
from .agents.state import atomic_json

class IncidentStore:
    def __init__(self, root: Path):
        self.root=root; self.root.mkdir(parents=True, exist_ok=True)
    def create(self, repository: str, report: str, reproduction_command: str="") -> dict:
        if not isinstance(repository,str) or not repository.strip() or len(repository)>1024: raise ValueError("repository")
        if not isinstance(report,str) or not report.strip() or len(report)>4000: raise ValueError("report")
        if not isinstance(reproduction_command,str) or len(reproduction_command)>1000: raise ValueError("reproduction")
        record={"id":uuid4().hex[:12],"repository":repository.strip(),"report":report.strip(),
                "reproduction_command":reproduction_command.strip(),"status":"REPORTED",
                "created_at":datetime.now(timezone.utc).isoformat()}
        atomic_json(self.root/f"{record['id']}.json",record); return record
    def list(self) -> list[dict]:
        records=[]
        for path in self.root.glob("*.json"):
            try: records.append(json.loads(path.read_text()))
            except (OSError,ValueError): continue
        return sorted(records,key=lambda item:item["created_at"],reverse=True)

class WorkspaceAPI:
    def __init__(self, root: Path):
        self.store=IncidentStore(root); self.clients=set()
    def payload(self): return {"type":"incidents","items":self.store.list()}
    async def broadcast(self, event: dict):
        data=json.dumps(event)
        for client in list(self.clients):
            try: await client.send(data)
            except Exception: self.clients.discard(client)
    async def websocket(self, ws):
        self.clients.add(ws); await ws.send(json.dumps(self.payload()))
        try:
            async for raw in ws:
                try:
                    value=json.loads(raw); record=self.store.create(value.get("repository",""),value.get("report",""),value.get("reproduction_command",""))
                    await ws.send(json.dumps({"type":"incident_created","item":record}))
                    await self.broadcast(self.payload())
                except (ValueError,TypeError,json.JSONDecodeError):
                    await ws.send(json.dumps({"type":"incident_rejected","message":"Provide a repository and incident report."}))
        finally: self.clients.discard(ws)
    def handler(self, ui_root: Path):
        api=self
        class Handler(BaseHTTPRequestHandler):
            def reply(self,status,data,kind):
                self.send_response(status);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            def do_GET(self):
                if self.path=="/api/incidents": return self.reply(200,json.dumps(api.payload()).encode(),"application/json")
                name="index.html" if self.path=="/" else self.path.removeprefix("/workspace/") if self.path.startswith("/workspace/") else ""
                file=(ui_root/name).resolve()
                if ui_root not in file.parents or not file.is_file(): return self.reply(404,b"Not found","text/plain")
                kind="text/css" if file.suffix==".css" else "application/javascript" if file.suffix==".js" else "text/html; charset=utf-8"
                self.reply(200,file.read_bytes(),kind)
            def do_POST(self):
                if self.path!="/api/incidents": return self.reply(404,b"{}","application/json")
                body=self.rfile.read(min(int(self.headers.get("Content-Length","0")),7000)).decode()
                form=parse_qs(body)
                try: item=api.store.create((form.get("repository")or[""])[0],(form.get("report")or[""])[0],(form.get("reproduction_command")or[""])[0])
                except ValueError: return self.reply(400,b'{"message":"Provide a repository and incident report."}',"application/json")
                self.reply(201,json.dumps({"type":"incident_created","item":item}).encode(),"application/json")
            def log_message(self,*args): pass
        return Handler

def serve_workspace(root: Path, port: int=8875):
    api=WorkspaceAPI(root); ui_root=Path(__file__).parents[1]/"workspace_ui"
    server=ThreadingHTTPServer(("127.0.0.1",port),api.handler(ui_root));threading.Thread(target=server.serve_forever,daemon=True).start()
    async def run():
        async with serve(api.websocket,"127.0.0.1",port+1): await asyncio.Future()
    print(f"TraceRoot workspace: http://127.0.0.1:{port} WebSocket: ws://127.0.0.1:{port+1}",flush=True);asyncio.run(run())
