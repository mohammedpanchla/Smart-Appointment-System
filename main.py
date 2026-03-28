"""
main.py — FastAPI application entry point.
Starts the scheduler on startup, mounts all routers.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bot import router as bot_router
from scheduler import create_scheduler
from webhooks import router as cal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("✅ APScheduler started — 4 jobs active.")
    yield
    scheduler.shutdown(wait=False)
    logger.info("🛑 APScheduler stopped.")


app = FastAPI(
    title="Smart Appointment System",
    description="Cal.com + WhatsApp + Supabase — multi-clinic appointment automation",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(cal_router, prefix="/webhooks", tags=["Cal.com"])
app.include_router(bot_router, prefix="/webhooks", tags=["WhatsApp Bot"])


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "service": "Smart Appointment System v1.0.0"}
