from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import httpx


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# --- OpenAI Status Check ---
@api_router.get("/openai/status")
async def openai_status():
    """Check OpenAI API key status"""
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_WHISPER_KEY")
    if not key:
        return {"ok": False, "error": "missing_key"}
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"}
            )
        
        if r.status_code == 200:
            return {"ok": True}
        else:
            return {
                "ok": False,
                "status": r.status_code,
                "body": r.text[:200] if r.text else ""
            }
    except httpx.HTTPError as e:
        return {"ok": False, "error": "network_error", "detail": str(e)}


# --- Usage Tracking Models ---
class UsageAdd(BaseModel):
    minutes: float
    source: str = "voice"


# --- Usage API (MongoDB storage) ---
@api_router.post("/usage/add")
async def usage_add(payload: UsageAdd):
    """Add usage record for cost tracking"""
    if payload.minutes <= 0:
        return {"ok": False, "reason": "minutes<=0"}
    
    doc = {
        "ts": datetime.now(timezone.utc),
        "minutes": payload.minutes,
        "source": payload.source
    }
    
    try:
        # Store timestamp as ISO string for MongoDB
        doc_to_insert = {**doc}
        doc_to_insert['ts'] = doc['ts'].isoformat()
        await db.usage.insert_one(doc_to_insert)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error adding usage: {e}")
        return {"ok": False, "error": str(e)}


@api_router.get("/usage/stats")
async def usage_stats(month: Optional[str] = None):
    """Get usage statistics for a given month (YYYY-MM format, UTC)"""
    now = datetime.now(timezone.utc)
    
    # Parse month parameter or use current month
    if month:
        try:
            y, m = [int(x) for x in month.split("-")]
            start = datetime(y, m, 1, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    # Calculate next month boundary
    if start.month == 12:
        nxt = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        nxt = datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)
    
    total = 0.0
    
    try:
        # Query MongoDB for usage in the date range
        # Convert start and nxt to ISO strings for comparison
        start_iso = start.isoformat()
        nxt_iso = nxt.isoformat()
        
        cursor = db.usage.find(
            {"ts": {"$gte": start_iso, "$lt": nxt_iso}},
            {"minutes": 1, "_id": 0}
        )
        
        async for doc in cursor:
            try:
                total += float(doc.get("minutes", 0))
            except (ValueError, TypeError):
                pass
        
        return {
            "minutes": round(total, 3),
            "from": start.isoformat(),
            "to": nxt.isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting usage stats: {e}")
        return {
            "minutes": 0.0,
            "from": start.isoformat(),
            "to": nxt.isoformat(),
            "error": str(e)
        }

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()