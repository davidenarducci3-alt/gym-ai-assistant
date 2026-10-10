"""Gym AI Assistant: FastAPI + Claude (tool use) + SQLite in sola lettura."""
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import queries

load_dotenv()
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text(encoding="utf-8")
MAX_STEPS = 5

queries.init_db()
client = anthropic.Anthropic()  # legge ANTHROPIC_API_KEY dall'ambiente
app = FastAPI(title="Gym AI Assistant")


class Msg(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: list[Msg]


@app.post("/chat")
def chat(body: ChatIn):
    messages = [m.model_dump() for m in body.messages[-20:] if m.role in ("user", "assistant")]
    tools_used = []
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=1000, system=SYSTEM_PROMPT,
                                      tools=queries.anthropic_tool_defs(), messages=messages)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"reply": text, "tools_used": tools_used}
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                tools_used.append(b.name)
                out = queries.run_tool(b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})
    return {"reply": "Non sono riuscito a completare la richiesta. Riprova tra poco.", "tools_used": tools_used}


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
