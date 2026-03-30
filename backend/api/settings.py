"""
settings.py — GET /api/settings (public, read-only subset)
Used by the frontend to load promo title, dates, prize info.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lib import db

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "OPTIONS"], allow_headers=["*"])

PUBLIC_KEYS = {
    "campaign_start_date", "campaign_end_date",
    "prize_description", "promo_title", "draw_date",
}

@app.get("/api/settings")
async def get_public_settings():
    all_settings = db.get_settings()
    return {k: v for k, v in all_settings.items() if k in PUBLIC_KEYS}
