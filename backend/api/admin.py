"""
admin.py — Admin API endpoints
GET  /api/admin/entries       — List/search entries
GET  /api/admin/entries/csv   — Download CSV
GET  /api/admin/stats         — Entry counts by status
GET  /api/admin/settings      — Get all settings
POST /api/admin/settings      — Update a setting
POST /api/admin/login         — Verify admin password
POST /api/admin/draw          — Run raffle draw
GET  /api/admin/draws         — List past draws
"""

import os
import sys
import csv
import io
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Query, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional

from lib import db

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST","DELETE","OPTIONS"], allow_headers=["*"])


def _auth(x_admin_password: Optional[str] = None) -> None:
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if not pw or x_admin_password != pw:
        raise HTTPException(401, "Unauthorized.")


# ── Login ─────────────────────────────────────────────────────
@app.post("/api/admin/login")
async def login(body: dict = Body(...)):
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if body.get("password") == pw:
        return {"success": True}
    raise HTTPException(401, "Wrong password.")


# ── Stats ─────────────────────────────────────────────────────
@app.get("/api/admin/stats")
async def stats(x_admin_password: Optional[str] = Header(None)):
    _auth(x_admin_password)
    return {
        "total":    db.count_entries(),
        "pending":  db.count_entries("pending"),
        "verified": db.count_entries("verified"),
        "rejected": db.count_entries("rejected"),
    }


# ── Entries list ──────────────────────────────────────────────
@app.get("/api/admin/entries")
async def list_entries(
    status:             Optional[str] = Query(None),
    limit:              int           = Query(100, ge=1, le=500),
    offset:             int           = Query(0, ge=0),
    x_admin_password:   Optional[str] = Header(None),
):
    _auth(x_admin_password)
    if status and status not in ("pending", "verified", "rejected"):
        raise HTTPException(422, "Invalid status filter.")
    entries = db.get_entries(status=status, limit=limit, offset=offset)
    total   = db.count_entries(status)
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@app.get("/api/admin/entries/csv")
async def export_csv(
    status:           Optional[str] = Query(None),
    x_admin_password: Optional[str] = Header(None),
):
    _auth(x_admin_password)
    entries = db.get_entries(status=status, limit=10000, offset=0)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "name", "email", "phone", "purchase_date",
        "invoice_number", "verification_status", "rejection_reason", "created_at"
    ], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(entries)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=raffle_entries.csv"},
    )


# ── Delete entry ──────────────────────────────────────────────
@app.delete("/api/admin/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    x_admin_password: Optional[str] = Header(None),
):
    _auth(x_admin_password)
    try:
        client = db.get_client()
        client.table("entries").delete().eq("id", entry_id).execute()
        return {"success": True, "deleted": entry_id}
    except Exception as e:
        raise HTTPException(500, f"Failed to delete entry: {e}")


# ── Settings ──────────────────────────────────────────────────
@app.get("/api/admin/settings")
async def get_settings(x_admin_password: Optional[str] = Header(None)):
    _auth(x_admin_password)
    return db.get_settings()


@app.post("/api/admin/settings")
async def update_settings(
    body:             dict         = Body(...),
    x_admin_password: Optional[str] = Header(None),
):
    _auth(x_admin_password)
    allowed_keys = {
        "campaign_start_date", "campaign_end_date",
        "required_product_keywords", "prize_description",
        "promo_title", "draw_date",
    }
    updated = []
    for key, value in body.items():
        if key in allowed_keys:
            db.update_setting(key, str(value))
            updated.append(key)
    return {"updated": updated}


# ── Raffle Draw ───────────────────────────────────────────────
@app.get("/api/admin/draw/pool")
async def draw_pool(x_admin_password: Optional[str] = Header(None)):
    """Return all verified entries (names only) for the animated draw."""
    _auth(x_admin_password)
    entries = db.get_verified_entries_for_draw()
    return {
        "count": len(entries),
        "entries": [{"id": e["id"], "name": e["name"]} for e in entries],
    }


@app.post("/api/admin/draw")
async def run_draw(
    body:             dict         = Body(default={}),
    x_admin_password: Optional[str] = Header(None),
):
    """Pick a random winner from verified entries."""
    _auth(x_admin_password)
    entries = db.get_verified_entries_for_draw()
    if not entries:
        raise HTTPException(400, "No verified entries to draw from.")

    winner = random.choice(entries)
    draw   = db.record_draw(winner["id"], body.get("notes", ""))

    return {
        "success":  True,
        "draw_id":  draw["id"],
        "drawn_at": draw["drawn_at"],
        "winner": {
            "id":             winner["id"],
            "name":           winner["name"],
            "email":          winner["email"],
            "phone":          winner["phone"],
            "invoice_number": winner.get("invoice_number", ""),
        },
    }


@app.get("/api/admin/draws")
async def list_draws(x_admin_password: Optional[str] = Header(None)):
    _auth(x_admin_password)
    return {"draws": db.get_draws()}
