from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import os, json, httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

app = FastAPI(title="raspberry-app API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

BASE_DIR = os.path.dirname(__file__)
USAGE_PATH  = os.getenv("USAGE_STORE_PATH",  os.path.join(BASE_DIR, "usage_store.json"))
ERRORS_PATH = os.getenv("ERRORS_STORE_PATH", os.path.join(BASE_DIR, "errors_store.json"))

def _load_list(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_list(path: str, data: List[Dict[str, Any]]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

_usage  : List[Dict[str, Any]] = _load_list(USAGE_PATH)
_errors : List[Dict[str, Any]] = _load_list(ERRORS_PATH)

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}

# --- OpenAI status ---
@app.get("/api/openai/status")
async def openai_status() -> Dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_WHISPER_KEY")
    if not key:
        return {"ok": False, "error": "missing_key"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.openai.com/v1/models",
                                 headers={"Authorization": f"Bearer {key}"})
        if r.status_code == 200:
            return {"ok": True}
        return {"ok": False, "status": r.status_code, "body": (r.text[:200] if r.text else "")}
    except httpx.HTTPError as e:
        return {"ok": False, "error": "network_error", "detail": str(e)}

# --- Usage: add/stats/list ---
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
    _save_list(USAGE_PATH, _usage)
    return {"ok": True}

@app.get("/api/usage/stats")
def usage_stats(month: Optional[str] = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if month:
        y, m = [int(x) for x in month.split("-")]
        start = datetime(y, m, 1, tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(start.year + (1 if start.month == 12 else 0),
                   1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)
    total = 0.0
    for e in _usage:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end:
                total += float(e.get("minutes", 0))
        except Exception:
            pass
    return {"minutes": round(total, 3), "from": start.isoformat(), "to": end.isoformat()}

@app.get("/api/usage/list")
def usage_list(month: Optional[str] = None, source: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if month:
        y, m = [int(x) for x in month.split("-")]
        start = datetime(y, m, 1, tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(start.year + (1 if start.month == 12 else 0),
                   1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)

    items: List[Dict[str, Any]] = []
    for e in _usage:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end and (not source or str(e.get("source")) == source):
                items.append(e)
        except Exception:
            continue
    items.sort(key=lambda d: d.get("ts",""), reverse=True)
    return {"items": items[:max(1,min(limit,1000))], "count": len(items)}

# --- Error telemetry: add/get ---
@app.post("/api/usage/error")
def error_add(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": str(payload.get("message","")),
        "where": str(payload.get("where","frontend")),
        "detail": payload.get("detail"),
    }
    _errors.append(entry)
    _save_list(ERRORS_PATH, _errors)
    return {"ok": True}

@app.get("/api/usage/errors")
def errors_list(month: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if month:
        y, m = [int(x) for x in month.split("-")]
        start = datetime(y, m, 1, tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(start.year + (1 if start.month == 12 else 0),
                   1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)
    items: List[Dict[str, Any]] = []
    for e in _errors:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end:
                items.append(e)
        except Exception:
            continue
    items.sort(key=lambda d: d.get("ts",""), reverse=True)
    return {"items": items[:max(1,min(limit,500))], "count": len(items)}
