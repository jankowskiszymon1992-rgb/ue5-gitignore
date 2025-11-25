from fastapi import FastAPI, Body, Query, Request, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
import os, json, httpx, io, csv, time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Imports for auth
try:
    import bcrypt
    import jwt as pyjwt
    import secrets
except ImportError:
    print("Installing bcrypt and PyJWT...")
    import subprocess
    subprocess.check_call(['pip', 'install', '-q', 'bcrypt==4.1.2', 'PyJWT==2.9.0'])
    import bcrypt
    import jwt as pyjwt
    import secrets

# ---- App & CORS ----
app = FastAPI(title="raspberry-app API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# ---- Paths & stores ----
BASE_DIR = os.path.dirname(__file__)
def p(name: str): return os.path.join(BASE_DIR, name)
USAGE_PATH   = os.getenv("USAGE_STORE_PATH",  p("usage_store.json"))
ERR_PATH     = os.getenv("ERRORS_STORE_PATH", p("errors_store.json"))
USERS_PATH   = os.getenv("USERS_STORE_PATH",  p("users_store.json"))
PROJ_PATH    = os.getenv("PROJECTS_STORE_PATH", p("projects_store.json"))
CLI_PATH     = os.getenv("CLIENTS_STORE_PATH",  p("clients_store.json"))
ADS_PATH     = os.getenv("JOBADS_STORE_PATH",   p("jobads_store.json"))

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
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_usage   : List[Dict[str, Any]] = _load_list(USAGE_PATH)
_errors  : List[Dict[str, Any]] = _load_list(ERR_PATH)
_users   : List[Dict[str, Any]] = _load_list(USERS_PATH)
_projects: List[Dict[str, Any]] = _load_list(PROJ_PATH)
_clients : List[Dict[str, Any]] = _load_list(CLI_PATH)
_ads     : List[Dict[str, Any]] = _load_list(ADS_PATH)

# ---- Bootstrap admin user if none ----
if not _users:
    salt = bcrypt.gensalt()
    pwd  = bcrypt.hashpw("admin123".encode(), salt).decode()
    _users = [{"id": 1, "username": "admin", "password": pwd, "role": "admin"}]
    _save_list(USERS_PATH, _users)
    print("✅ Created admin user: admin/admin123")

# ---- Seed data ----
if not _clients:
    _clients = [
        {"id": 1, "name": "Firma ABC Sp. z o.o."},
        {"id": 2, "name": "Przedsiębiorstwo XYZ"}
    ]
    _save_list(CLI_PATH, _clients)
    print("✅ Created 2 demo clients")

if not _projects:
    _projects = [
        {"id": 1, "name": "Instalacja elektryczna - Biurowiec", "status": "active", "hours_month": 120, "client_id": 1},
        {"id": 2, "name": "Modernizacja sieci - Magazyn", "status": "active", "hours_month": 80, "client_id": 1},
        {"id": 3, "name": "Projekt oświetlenia LED", "status": "completed", "hours_month": 0, "client_id": 2}
    ]
    _save_list(PROJ_PATH, _projects)
    print("✅ Created 3 demo projects")

if not _ads:
    _ads = [
        {"id": 1, "title": "Elektryk - doświadczony", "description": "Poszukujemy elektryka z uprawnieniami", "ts": datetime.now(timezone.utc).isoformat()},
        {"id": 2, "title": "Pomocnik elektryka", "description": "Praca na budowie", "ts": datetime.now(timezone.utc).isoformat()}
    ]
    _save_list(ADS_PATH, _ads)
    print("✅ Created 2 demo job ads")

# ---- Helpers ----
def now_utc() -> datetime: return datetime.now(timezone.utc)

def parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    try:
        y,m,d = [int(x) for x in s.split("-")]
        return datetime(y,m,d,tzinfo=timezone.utc)
    except Exception:
        return None

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(16))

def make_jwt(user: Dict[str, Any]) -> str:
    payload = {"sub": user["username"], "role": user.get("role","user"), "exp": datetime.utcnow() + timedelta(days=7)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")

def current_user(request: Request) -> Optional[Dict[str,Any]]:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            data = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            u = next((x for x in _users if x["username"]==data["sub"]), None)
            return u
        except Exception:
            return None
    return None

# ---- Optional admin token (for exports) ----
def require_admin_token(request: Request):
    expected = os.getenv("ADMIN_TOKEN")
    if not expected: return
    auth = request.headers.get("authorization") or ""
    token = None
    if auth.lower().startswith("bearer "): token = auth[7:].strip()
    token = token or request.headers.get("x-admin-token") or request.query_params.get("token")
    if token != expected: raise HTTPException(status_code=401, detail="unauthorized")

# ---- Simple rate limit ----
class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity; self.refill = refill_per_sec
        self.buckets: Dict[str, Tuple[float, float]] = {}
    
    def allow(self, key: str) -> Tuple[bool, float]:
        now = time.time()
        tokens, last = self.buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens < 1.0:
            need = 1.0 - tokens
            retry = need / self.refill if self.refill>0 else 60.0
            self.buckets[key] = (tokens, now)
            return False, max(1.0, retry)
        self.buckets[key] = (tokens - 1.0, now)
        return True, 0.0

rate_usage_add = TokenBucket(30, 0.5)
rate_error_add = TokenBucket(30, 0.5)

def client_ip(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for")
    return xff.split(",")[0].strip() if xff else (req.client.host if req.client else "unknown")

def enforce_rl(req: Request, which: str):
    ip = client_ip(req)
    ok_rl, retry = (rate_usage_add if which=="usage_add" else rate_error_add).allow(f"{ip}:{which}")
    if not ok_rl: 
        raise HTTPException(status_code=429, detail="rate_limited", headers={"Retry-After": str(int(retry))})

# ---- Health ----
@app.get("/health")
def health(): 
    return {"ok": True, "time": now_utc().isoformat()}

# ---- Auth ----
@app.post("/api/auth/login")
def login(payload: Dict[str, Any] = Body(...)):
    u = next((x for x in _users if x["username"] == str(payload.get("username",""))), None)
    if not u: 
        raise HTTPException(status_code=401, detail="bad_credentials")
    if not bcrypt.checkpw(str(payload.get("password","")).encode(), u["password"].encode()):
        raise HTTPException(status_code=401, detail="bad_credentials")
    return {"token": make_jwt(u), "user": {"username": u["username"], "role": u.get("role","user")}}

@app.get("/api/auth/me")
def me(request: Request):
    u = current_user(request)
    if not u: 
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"user": {"username": u["username"], "role": u.get("role","user")}}

# ---- OpenAI status ----
@app.get("/api/openai/status")
async def openai_status():
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_WHISPER_KEY")
    if not key: 
        return {"ok": False, "error": "missing_key"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
        return {"ok": r.status_code == 200, "status": r.status_code}
    except httpx.HTTPError as e:
        return {"ok": False, "error": "network_error", "detail": str(e)}

# ---- Usage / telemetry ----
@app.post("/api/usage/add")
def usage_add(request: Request, payload: Dict[str, Any] = Body(...)):
    enforce_rl(request, "usage_add")
    try: 
        minutes = float(payload.get("minutes", 0))
    except Exception: 
        minutes = 0.0
    if minutes <= 0: 
        return {"ok": False, "reason": "minutes<=0"}
    entry = {"ts": now_utc().isoformat(), "minutes": round(minutes, 4), "source": str(payload.get("source","voice"))}
    _usage.append(entry)
    _save_list(USAGE_PATH, _usage)
    return {"ok": True}

@app.get("/api/usage/stats")
def usage_stats(month: Optional[str] = None, from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    now = now_utc()
    if from_ or to:
        start = parse_date(from_) or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = (parse_date(to) or now) + timedelta(days=1)
    else:
        if month:
            y,m = [int(x) for x in month.split("-")]
            start = datetime(y,m,1,tzinfo=timezone.utc)
        else:
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = datetime(start.year + (1 if start.month==12 else 0), 1 if start.month==12 else start.month+1, 1, tzinfo=timezone.utc)
    
    total = 0.0
    for e in _usage:
        try:
            ts = datetime.fromisoformat(e["ts"]).astimezone(timezone.utc)
            if start <= ts < end: 
                total += float(e.get("minutes",0))
        except Exception: 
            pass
    return {"minutes": round(total,3), "from": start.isoformat(), "to": (end - timedelta(seconds=1)).isoformat()}

@app.get("/api/usage/list")
def usage_list(
    month: Optional[str] = None, 
    from_: Optional[str] = Query(None, alias="from"), 
    to: Optional[str] = None,
    source: Optional[str] = None, 
    page: int = 1, 
    page_size: int = 20, 
    sort: str = "desc"
):
    now = now_utc()
    if from_ or to:
        start = parse_date(from_) or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = (parse_date(to) or now) + timedelta(days=1)
    else:
        if month:
            y,m = [int(x) for x in month.split("-")]
            start = datetime(y,m,1,tzinfo=timezone.utc)
        else:
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = datetime(start.year + (1 if start.month==12 else 0), 1 if start.month==12 else start.month+1, 1, tzinfo=timezone.utc)
    
    ps = max(1, min(page_size, 1000))
    p = max(1, page)
    
    items = []
    for e in _usage:
        try:
            ts = datetime.fromisoformat(e["ts"]).astimezone(timezone.utc)
            if start <= ts < end and (not source or e.get("source")==source): 
                items.append(e)
        except Exception: 
            pass
    
    items.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    total = len(items)
    s=(p-1)*ps
    e_idx=s+ps
    return {"items": items[s:e_idx], "total": total, "page": p, "page_size": ps, "pages": (total+ps-1)//ps}

@app.post("/api/usage/error")
def error_add(request: Request, payload: Dict[str, Any] = Body(...)):
    enforce_rl(request, "error_add")
    entry = {
        "ts": now_utc().isoformat(), 
        "message": str(payload.get("message","")), 
        "where": str(payload.get("where","frontend")), 
        "detail": payload.get("detail")
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
    sort: str = "desc"
):
    now = now_utc()
    if from_ or to:
        start = parse_date(from_) or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = (parse_date(to) or now) + timedelta(days=1)
    else:
        if month:
            y,m = [int(x) for x in month.split("-")]
            start = datetime(y,m,1,tzinfo=timezone.utc)
        else:
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = datetime(start.year + (1 if start.month==12 else 0), 1 if start.month==12 else start.month+1, 1, tzinfo=timezone.utc)
    
    ps = max(1, min(page_size, 1000))
    p = max(1, page)
    
    items = []
    for e in _errors:
        try:
            ts = datetime.fromisoformat(e["ts"]).astimezone(timezone.utc)
            if start <= ts < end: 
                items.append(e)
        except Exception: 
            pass
    
    items.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    total = len(items)
    s=(p-1)*ps
    e_idx=s+ps
    return {"items": items[s:e_idx], "total": total, "page": p, "page_size": ps, "pages": (total+ps-1)//ps}

# ---- Server exports ----
def _filter_usage(from_, to, source, sort):
    now = now_utc()
    start = parse_date(from_) or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end   = (parse_date(to) or now) + timedelta(days=1)
    rows = []
    for e in _usage:
        try:
            ts = datetime.fromisoformat(e["ts"]).astimezone(timezone.utc)
            if start <= ts < end and (not source or e.get("source")==source): 
                rows.append(e)
        except Exception: 
            pass
    rows.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    return rows

def _filter_errors(from_, to, sort):
    now = now_utc()
    start = parse_date(from_) or datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end   = (parse_date(to) or now) + timedelta(days=1)
    rows = []
    for e in _errors:
        try:
            ts = datetime.fromisoformat(e["ts"]).astimezone(timezone.utc)
            if start <= ts < end: 
                rows.append(e)
        except Exception: 
            pass
    rows.sort(key=lambda d: d.get("ts",""), reverse=(sort!="asc"))
    return rows

@app.get("/api/usage/export.csv")
def usage_export_csv(
    from_: Optional[str] = Query(None, alias="from"), 
    to: Optional[str] = None, 
    source: Optional[str] = None, 
    sort: str = "desc", 
    _=Depends(require_admin_token)
):
    rows = _filter_usage(from_, to, source, sort)
    def gen():
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["ts","minutes","source"])
        yield out.getvalue()
        out.seek(0)
        out.truncate(0)
        for r in rows: 
            w.writerow([r.get("ts",""), r.get("minutes",0), r.get("source","")])
            yield out.getvalue()
            out.seek(0)
            out.truncate(0)
    return StreamingResponse(gen(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="usage_{from_ or "auto"}_{to or "now"}{f"_{source}" if source else ""}.csv"'})

@app.get("/api/usage/export.xlsx")
def usage_export_xlsx(
    from_: Optional[str] = Query(None, alias="from"), 
    to: Optional[str] = None, 
    source: Optional[str] = None, 
    sort: str = "desc", 
    _=Depends(require_admin_token)
):
    from openpyxl import Workbook
    rows = _filter_usage(from_, to, source, sort)
    wb = Workbook()
    ws = wb.active
    ws.title = "Usage"
    ws.append(["ts","minutes","source"])
    for r in rows: 
        ws.append([r.get("ts",""), r.get("minutes",0), r.get("source","")])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(), 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="usage_{from_ or "auto"}_{to or "now"}{f"_{source}" if source else ""}.xlsx"'}
    )

@app.get("/api/errors/export.csv")
def errors_export_csv(
    from_: Optional[str] = Query(None, alias="from"), 
    to: Optional[str] = None, 
    sort: str = "desc", 
    _=Depends(require_admin_token)
):
    rows = _filter_errors(from_, to, sort)
    def gen():
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["ts","where","message"])
        yield out.getvalue()
        out.seek(0)
        out.truncate(0)
        for r in rows: 
            w.writerow([r.get("ts",""), r.get("where",""), r.get("message","")])
            yield out.getvalue()
            out.seek(0)
            out.truncate(0)
    return StreamingResponse(gen(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="errors_{from_ or "auto"}_{to or "now"}.csv"'})

@app.get("/api/errors/export.xlsx")
def errors_export_xlsx(
    from_: Optional[str] = Query(None, alias="from"), 
    to: Optional[str] = None, 
    sort: str = "desc", 
    _=Depends(require_admin_token)
):
    from openpyxl import Workbook
    rows = _filter_errors(from_, to, sort)
    wb = Workbook()
    ws = wb.active
    ws.title = "Errors"
    ws.append(["ts","where","message"])
    for r in rows: 
        ws.append([r.get("ts",""), r.get("where",""), r.get("message","")])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(), 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="errors_{from_ or "auto"}_{to or "now"}.xlsx"'}
    )

# ---- Projects/Clients + Stats ----
def _next_id(coll: List[Dict[str,Any]]) -> int: 
    return (max([c.get("id",0) for c in coll]) + 1) if coll else 1

@app.get("/api/projects/stats")
def projects_stats():
    total_clients   = len(_clients)
    total_projects  = len(_projects)
    active_projects = sum(1 for p in _projects if p.get("status")=="active")
    completed_projects = sum(1 for p in _projects if p.get("status")=="completed")
    total_hours_month = int(sum(float(p.get("hours_month",0)) for p in _projects if p.get("status")=="active"))
    return {
        "total_clients": total_clients, 
        "total_projects": total_projects, 
        "active_projects": active_projects,
        "completed_projects": completed_projects, 
        "total_hours_month": total_hours_month
    }

@app.get("/api/projects")
def projects_list(): 
    return {"items": _projects}

@app.post("/api/projects")
def projects_add(payload: Dict[str, Any] = Body(...)):
    item = {
        "id": _next_id(_projects), 
        "name": payload.get("name","Projekt"), 
        "status": payload.get("status","active"),
        "hours_month": float(payload.get("hours_month",0)), 
        "client_id": int(payload.get("client_id",0))
    }
    _projects.append(item)
    _save_list(PROJ_PATH, _projects)
    return {"ok": True, "data": item}

@app.patch("/api/projects/{pid}")
def projects_patch(pid: int, payload: Dict[str, Any] = Body(...)):
    p = next((x for x in _projects if x["id"]==pid), None)
    if not p: 
        raise HTTPException(404)
    p.update({k:v for k,v in payload.items() if k in ("name","status","hours_month","client_id")})
    _save_list(PROJ_PATH, _projects)
    return {"ok": True, "data": p}

@app.get("/api/clients")
def clients_list(): 
    return {"items": _clients}

@app.post("/api/clients")
def clients_add(payload: Dict[str, Any] = Body(...)):
    item = {"id": _next_id(_clients), "name": payload.get("name","Klient")}
    _clients.append(item)
    _save_list(CLI_PATH, _clients)
    return {"ok": True, "data": item}

# ---- Job Ads (CRUD) ----
@app.get("/api/jobads")
def ads_list(): 
    return {"items": _ads}

@app.post("/api/jobads")
def ads_add(payload: Dict[str, Any] = Body(...)):
    item = {
        "id": _next_id(_ads), 
        "title": payload.get("title","Stanowisko"), 
        "description": payload.get("description",""), 
        "ts": now_utc().isoformat()
    }
    _ads.append(item)
    _save_list(ADS_PATH, _ads)
    return {"ok": True, "data": item}

@app.delete("/api/jobads/{aid}")
def ads_del(aid: int):
    idx = next((i for i,a in enumerate(_ads) if a["id"]==aid), -1)
    if idx<0: 
        raise HTTPException(404)
    _ads.pop(idx)
    _save_list(ADS_PATH, _ads)
    return {"ok": True}

# ---- Weather (OpenWeather or demo) ----
@app.get("/api/weather/forecast")
async def weather_forecast():
    key = os.getenv("OPENWEATHER_API_KEY")
    city = os.getenv("OPENWEATHER_CITY","Warsaw,PL")
    if not key:
        # demo response
        return {
            "current": {"temp": 6, "description": "pochmurno", "humidity": 80, "wind_speed": 3, "icon": "03d"},
            "daily": [
                {"date": now_utc().date().isoformat(), "temp_max": 8, "temp_min": 3, "description": "zachmurzenie", "icon": "03d"},
                {"date": (now_utc()+timedelta(days=1)).date().isoformat(), "temp_max": 7, "temp_min": 2, "description": "przelotne opady", "icon": "10d"},
                {"date": (now_utc()+timedelta(days=2)).date().isoformat(), "temp_max": 6, "temp_min": 1, "description": "zachmurzenie", "icon": "03d"},
                {"date": (now_utc()+timedelta(days=3)).date().isoformat(), "temp_max": 5, "temp_min": 0, "description": "słonecznie", "icon": "01d"},
                {"date": (now_utc()+timedelta(days=4)).date().isoformat(), "temp_max": 7, "temp_min": 2, "description": "częściowe zachmurzenie", "icon": "02d"},
                {"date": (now_utc()+timedelta(days=5)).date().isoformat(), "temp_max": 8, "temp_min": 3, "description": "deszcz", "icon": "09d"},
                {"date": (now_utc()+timedelta(days=6)).date().isoformat(), "temp_max": 6, "temp_min": 1, "description": "zachmurzenie", "icon": "03d"},
            ]
        }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.openweathermap.org/data/2.5/forecast", params={"q": city, "appid": key, "units": "metric", "lang": "pl"})
        if r.status_code != 200: 
            return {"error": "openweather_fail", "status": r.status_code}
        data = r.json()
        # Simple aggregation to daily (7 days)
        days: Dict[str, Dict[str, Any]] = {}
        for it in data.get("list", []):
            dt = datetime.fromtimestamp(it["dt"], tz=timezone.utc).date().isoformat()
            main = it.get("main", {})
            weather = (it.get("weather") or [{}])[0]
            d = days.setdefault(dt, {"temp_max": -1e9, "temp_min": 1e9, "icon": weather.get("icon","01d"), "description": weather.get("description","")})
            d["temp_max"] = max(d["temp_max"], main.get("temp_max", main.get("temp",0)))
            d["temp_min"] = min(d["temp_min"], main.get("temp_min", main.get("temp",0)))
            d["icon"] = weather.get("icon","01d")
            d["description"] = weather.get("description","")
        daily = [{"date": k, **v} for k,v in sorted(days.items())][:7]
        current = {
            "temp": int(daily[0]["temp_max"]) if daily else 0,
            "description": daily[0]["description"] if daily else "",
            "humidity": 60, 
            "wind_speed": 3, 
            "icon": daily[0]["icon"] if daily else "01d"
        }
        return {"current": current, "daily": daily}
    except httpx.HTTPError as e:
        return {"error": "network_error", "detail": str(e)}

# ---- Voice transcribe (OpenAI Whisper or MOCK) ----
@app.post("/api/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_WHISPER_KEY")
    if not key:
        return {"text": "MOCK: brak klucza OpenAI – transkrypcja testowa."}
    try:
        content = await file.read()
        
        form_data = {
            "model": (None, "whisper-1"),
            "file": (file.filename or "audio.webm", content, file.content_type or "audio/webm")
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files=form_data
            )
        
        if r.status_code == 200:
            j = r.json()
            return {"text": j.get("text","")}
        else:
            return {"text": f"Błąd transkrypcji: {r.status_code}"}
    except Exception as e:
        return {"text": f"Transkrypcja nie powiodła się: {e}"}

print("🚀 Raspberry App API Ready!")
print("📝 Admin credentials: admin / admin123")
print("🌍 Demo data loaded: 2 clients, 3 projects, 2 job ads")
