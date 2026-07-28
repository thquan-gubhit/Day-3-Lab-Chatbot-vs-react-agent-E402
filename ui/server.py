"""
🖥️ GIAO DIỆN DEMO — FastAPI + 1 trang HTML tĩnh

Điểm quan trọng khi demo: panel bên phải stream TỪNG BƯỚC
Thought → Action → Observation theo thời gian thực (Server-Sent Events).
Người xem thấy được agent đang suy nghĩ gì, gọi tool nào, nhận về gì —
tức là thấy được BẰNG CHỨNG, không chỉ thấy câu trả lời cuối.

Chạy:
    python ui/server.py
    → mở http://127.0.0.1:8000
"""

import json
import os
import queue
import sys
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import listing_store as store
import tools as tools_mod
from app import load_test_cases, run_baseline_chatbot, run_react_agent
from memory import AgentMemory
from prompts import MAX_ITERATIONS
from providers import get_llm_provider

app = FastAPI(title="Trợ lý so sánh phòng trọ — Lab 3 E402")

PROVIDER = get_llm_provider()
tools_mod.set_provider(PROVIDER)

STATIC_DIR = os.path.join(BASE_DIR, "ui", "static")
app.mount("/anh", StaticFiles(directory=os.path.join(BASE_DIR, "config", "assets", "rooms")),
          name="anh")

# Bộ nhớ hội thoại theo phiên (Cấp 4) — demo được tính năng nhớ qua nhiều lượt
SESSIONS = {}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/meta")
def meta():
    listings = store.all_listings()
    return {
        "provider": PROVIDER.__class__.__name__,
        "model": getattr(PROVIDER, "model_name", "mock"),
        "n_listings": len(listings),
        "max_iterations": MAX_ITERATIONS,
        "tools": list(tools_mod.AVAILABLE_TOOLS.keys()),
        "test_cases": [
            {"id": c["id"], "category": c["category"], "question": c["question"],
             "attack_type": c.get("attack_type")}
            for c in load_test_cases()
        ],
    }


@app.get("/api/listings")
def listings(limit: int = 24):
    out = []
    for l in store.all_listings()[:limit]:
        out.append({
            "id": l["id"], "khu_vuc": l["khu_vuc"], "quan": l["quan"],
            "author": l["author"], "posted_at": l["posted_at"],
            "status": l["status"], "duplicate_of": l["duplicate_of"],
            "image_only_price": bool(l["image_only_price"]),
            "raw_text": l["raw_text"],
            "image": f"/anh/{l['id']}.png",
        })
    return out


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/ask")
def ask(q: str, mode: str = "agent", session: str = "default"):
    """Chạy agent trong thread riêng, đẩy từng sự kiện ra SSE."""
    events = queue.Queue()
    mem = SESSIONS.setdefault(session, AgentMemory())

    def on_event(kind, payload):
        events.put((kind, payload))

    def worker():
        try:
            if mode == "chatbot":
                tr = run_baseline_chatbot(q, PROVIDER, on_event=on_event)
            else:
                mem.observe_user_message(q)
                tr = run_react_agent(q, PROVIDER, on_event=on_event,
                                     memory_block=mem.as_prompt_block())
                mem.remember_result(q, tr.final_answer)
            events.put(("done", {"trace": tr.to_dict(), "memory": mem.summary()}))
        except Exception as e:  # không để lỗi làm treo stream
            events.put(("error", {"message": f"{type(e).__name__}: {e}"}))
            events.put(("done", {"trace": None, "memory": mem.summary()}))

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        yield _sse("open", {"mode": mode})
        while True:
            kind, payload = events.get()
            yield _sse(kind, payload)
            if kind == "done":
                break

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/reset")
def reset(session: str = "default"):
    SESSIONS.pop(session, None)
    return JSONResponse({"ok": True})


def _free_port(start=8000, tries=20):
    """Máy có thể đang chạy sẵn app khác ở cổng 8000 — tự tìm cổng trống kế tiếp."""
    import socket
    for p in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("UI_PORT") or 0) or _free_port()
    print("=" * 64)
    print("🏠 TRỢ LÝ SO SÁNH PHÒNG TRỌ — Lab 3 Nhóm E402")
    print(f"   Provider: {PROVIDER.__class__.__name__} "
          f"({getattr(PROVIDER, 'model_name', 'mock')})")
    print(f"   Kho dữ liệu: {len(store.all_listings())} bài đăng")
    print(f"   ➜  http://127.0.0.1:{port}")
    print("=" * 64)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
