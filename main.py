from fastapi import FastAPI
from pydantic import BaseModel
class Command(BaseModel):
 type: str
 value: str
app = FastAPI()
@app.get("/health")
def health():
 return {"status": "ok"}
@app.post("/command")
def command(cmd: Command):
 print(f": { cmd.type } = { cmd.value }")
 return {"result": "ok", "received": cmd}
from fastapi import FastAPI, WebSocket
app = FastAPI() 
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"echo: {data}")