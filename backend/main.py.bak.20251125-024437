from fastapi import FastAPI, Body, Query, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
import os, json, httpx, io, csv, time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

app = FastAPI(title="raspberry-app API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

BASE_DIR   = os.path.dirname(__file__)
USAGE_PATH = os.getenv("USAGE_STORE_PATH",  os.path.join(BASE_DIR, "usage_store.json"))
ERR_PATH   = os.getenv("ERRORS_STORE_PATH", os.path.join(BASE_DIR, "errors_store.json"))

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

def _parse_date_utc(s: str) -> Optional[datetime]:
    try:
        y, m, d = [int(x) for x in s.split("-")]
        return datetime(y, m, d, tzinfo=timezone.utc)
    except Exception:
        return None

_usage  : List[Dict[str, Any]] = _load_list(USAGE_PATH)
_errors : List[Dict[str, Any]] = _load_list(ERR_PATH)

# ---------- Auth (opcjonalny token admin) ----------
def require_admin(request: Request):
    expected = os.getenv("ADMIN_TOKEN")
    if not expected:
        return
    auth = request.headers.get("authorization") or ""
    token = None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    token = token or request.headers.get("x-admin-token") or request.query_params.get("token")
    if token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

# ---------- Rate limiter (token bucket) ----------
class TokenBucket:
    # why: prosty, tani limiter in-memory
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill = refill_per_sec
        self.buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_ts)

    def allow(self, key: str) -> Tuple[bool, float]:
        now = time.time()
        tokens, last = self.buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens < 1.0:
            # retry after (seconds) – dla 429 header
            need = 1.0 - tokens
            retry = need / self.refill if self.refill > 0 else 60.0
            self.buckets[key] = (tokens, now)
            return False, max(1.0, retry)
        self.buckets[key] = (tokens - 1.0, now)
        return True, 0.0

rate_usage_add  = TokenBucket(capacity=30, refill_per_sec=0.5)  # 30/min
rate_error_add  = TokenBucket(capacity=30, refill_per_sec=0.5)  # 30/min

def client_ip(req: Request) -> str:
    # behind proxy X-Forwarded-For first IP if exists
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"

def enforce_rl(req: Request, which: str):
    ip = client_ip(req)
    if which == "usage_add":
        ok, retry = rate_usage_add.allow(f"{ip}:{which}")
    else:
        ok, retry = rate_error_add.allow(f"{ip}:{which}")
    if not ok:
        # 429 + Retry-After
        headers = {"Retry-After": str(int(retry))}
        raise HTTPException(status_code=429, detail="rate_limited", headers=headers)

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}

# ---- OpenAI status ----
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

# ---- Usage: add/stats/list ----
@app.post("/api/usage/add")
def usage_add(request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    enforce_rl(request, "usage_add")
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
def usage_stats(
    month: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if from_ or to:
        start = _parse_date_utc(from_) if from_ else datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end_base = _parse_date_utc(to) if to else now
        end = end_base + timedelta(days=1)
    else:
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
    return {"minutes": round(total, 3), "from": start.isoformat(), "to": (end - timedelta(seconds=1)).isoformat()}

@app.get("/api/usage/list")
def usage_list(
    month: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    source: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "desc",
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if from_ or to:
        start = _parse_date_utc(from_) if from_ else datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end_base = _parse_date_utc(to) if to else now
        end = end_base + timedelta(days=1)
    else:
        if month:
            y, m = [int(x) for x in month.split("-")]
            start = datetime(y, m, 1, tzinfo=timezone.utc)
        else:
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = datetime(start.year + (1 if start.month == 12 else 0),
                       1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)

    ps = max(1, min(page_size, 1000))
    p = max(1, page)

    items: List[Dict[str, Any]] = []
    for e in _usage:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end and (not source or str(e.get("source")) == source):
                items.append(e)
        except Exception:
            continue

    items.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    total = len(items)
    start_i = (p-1)*ps
    end_i = start_i + ps
    return {"items": items[start_i:end_i], "total": total, "page": p, "page_size": ps, "pages": (total+ps-1)//ps}

# ---- Errors: add/get ----
@app.post("/api/usage/error")
def error_add(request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    enforce_rl(request, "error_add")
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": str(payload.get("message","")),
        "where": str(payload.get("where","frontend")),
        "detail": payload.get("detail"),
    }
    _errors.append(entry)
    _save_list(ERR_PATH, _errors)
    return {"ok": True}

@app.get("/api/usage/errors")
def errors_list(
    month: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "desc",
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if from_ or to:
        start = _parse_date_utc(from_) if from_ else datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end_base = _parse_date_utc(to) if to else now
        end = end_base + timedelta(days=1)
    else:
        if month:
            y, m = [int(x) for x in month.split("-")]
            start = datetime(y, m, 1, tzinfo=timezone.utc)
        else:
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = datetime(start.year + (1 if start.month == 12 else 0),
                       1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)

    ps = max(1, min(page_size, 1000))
    p = max(1, page)

    items: List[Dict[str, Any]] = []
    for e in _errors:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end:
                items.append(e)
        except Exception:
            continue

    items.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    total = len(items)
    start_i = (p-1)*ps
    end_i = start_i + ps
    return {"items": items[start_i:end_i], "total": total, "page": p, "page_size": ps, "pages": (total+ps-1)//ps}

# ---- Filters helpers for export ----
def _filter_usage(from_: Optional[str], to: Optional[str], source: Optional[str], sort: str):
    now = datetime.now(timezone.utc)
    start = _parse_date_utc(from_) if from_ else datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end_base = _parse_date_utc(to) if to else now
    end = end_base + timedelta(days=1)
    rows = []
    for e in _usage:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end and (not source or str(e.get("source")) == source):
                rows.append(e)
        except Exception:
            continue
    rows.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    return rows

def _filter_errors(from_: Optional[str], to: Optional[str], sort: str):
    now = datetime.now(timezone.utc)
    start = _parse_date_utc(from_) if from_ else datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end_base = _parse_date_utc(to) if to else now
    end = end_base + timedelta(days=1)
    rows = []
    for e in _errors:
        try:
            ts = datetime.fromisoformat(str(e.get("ts"))).astimezone(timezone.utc)
            if start <= ts < end:
                rows.append(e)
        except Exception:
            continue
    rows.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    return rows

# ---- Server exports (require_admin if ADMIN_TOKEN set) ----
@app.get("/api/usage/export.csv")
def usage_export_csv(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    source: Optional[str] = None,
    sort: str = "desc",
    _=Depends(require_admin),
):
    rows = _filter_usage(from_, to, source, sort)
    def gen():
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(["ts","minutes","source"]); yield out.getvalue(); out.seek(0); out.truncate(0)
        for r in rows:
            w.writerow([r.get("ts",""), r.get("minutes",0), r.get("source","")])
            yield out.getvalue(); out.seek(0); out.truncate(0)
    filename = f'usage_{from_ or "auto"}_{to or "now"}{f"_{source}" if source else ""}.csv'
    return StreamingResponse(gen(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/api/usage/export.xlsx")
def usage_export_xlsx(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    source: Optional[str] = None,
    sort: str = "desc",
    _=Depends(require_admin),
):
    from openpyxl import Workbook
    rows = _filter_usage(from_, to, source, sort)
    wb = Workbook(); ws = wb.active; ws.title = "Usage"
    ws.append(["ts","minutes","source"])
    for r in rows:
        ws.append([r.get("ts",""), r.get("minutes",0), r.get("source","")])
    buf = io.BytesIO(); wb.save(buf)
    filename = f'usage_{from_ or "auto"}_{to or "now"}{f"_{source}" if source else ""}.xlsx'
    return Response(content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/api/errors/export.csv")
def errors_export_csv(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    sort: str = "desc",
    _=Depends(require_admin),
):
    rows = _filter_errors(from_, to, sort)
    def gen():
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(["ts","where","message"]); yield out.getvalue(); out.seek(0); out.truncate(0)
        for r in rows:
            w.writerow([r.get("ts",""), r.get("where",""), r.get("message","")])
            yield out.getvalue(); out.seek(0); out.truncate(0)
    filename = f'errors_{from_ or "auto"}_{to or "now"}.csv'
    return StreamingResponse(gen(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/api/errors/export.xlsx")
def errors_export_xlsx(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    sort: str = "desc",
    _=Depends(require_admin),
):
    from openpyxl import Workbook
    rows = _filter_errors(from_, to, sort)
    wb = Workbook(); ws = wb.active; ws.title = "Errors"
    ws.append(["ts","where","message"])
    for r in rows:
        ws.append([r.get("ts",""), r.get("where",""), r.get("message","")])
    buf = io.BytesIO(); wb.save(buf)
    filename = f'errors_{from_ or "auto"}_{to or "now"}.xlsx'
    return Response(content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
