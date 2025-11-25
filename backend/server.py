from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import os, json, httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

app = FastAPI(title="raspberry-app API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

STORE_PATH = os.getenv("USAGE_STORE_PATH", os.path.join(os.path.dirname(__file__), "usage_store.json"))

def _load_store(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def _save_store(path: str, data: List[Dict[str, Any]]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        # intentionally ignore write errors (read-only FS etc.)
        pass

_usage: List[Dict[str, Any]] = _load_store(STORE_PATH)

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/openai/status")
async def openai_status() -> Dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_WHISPER_KEY")
    if not key:
        return {"ok": False, "error": "missing_key"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code == 200:
            return {"ok": True}
        return {"ok": False, "status": r.status_code, "body": (r.text[:200] if r.text else "")}
    except httpx.HTTPError as e:
        return {"ok": False, "error": "network_error", "detail": str(e)}

@app.post("/api/usage/add")
def usage_add(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    try:
        minutes = float(payload.get("minutes", 0))
    except Exception:
        minutes = 0.0
    if minutes <= 0:
        return {"ok": False, "reason": "minutes<=0"}
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "minutes": round(minutes, 4),
        "source": str(payload.get("source", "voice")),
    }
    _usage.append(entry)
    _save_store(STORE_PATH, _usage)  # tania „trwałość" bez DB
    return {"ok": True}

@app.get("/api/usage/stats")
def usage_stats(month: Optional[str] = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if month:
        y, m = [int(x) for x in month.split("-")]
        start = datetime(y, m, 1, tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if start.month == 12:
        end = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)

    total = 0.0
    for e in _usage:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end:
                total += float(e.get("minutes", 0))
        except Exception:
            continue
    return {"minutes": round(total, 3), "from": start.isoformat(), "to": end.isoformat()}
