"""
draw.py — POST /api/admin/draw
Performs a random raffle draw from verified entries.
Protected by ADMIN_PASSWORD header.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from lib import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


def _check_admin_auth(x_admin_password: Optional[str] = Header(None)) -> None:
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_password or x_admin_password != admin_password:
        raise HTTPException(status_code=401, detail="Unauthorized. Invalid or missing admin password.")


class DrawRequest(BaseModel):
    confirm: bool = False  # Caller must explicitly set confirm=true to prevent accidental draws


@app.post("/api/admin/draw")
async def perform_draw(
    body: DrawRequest,
    x_admin_password: Optional[str] = Header(None),
):
    _check_admin_auth(x_admin_password)

    if not body.confirm:
        raise HTTPException(
            status_code=422,
            detail="Set 'confirm': true in the request body to perform the draw.",
        )

    # Count eligible entries first
    total_verified = db.count_entries(status="verified")
    draws = db.list_draws()
    already_won_ids = {d["winner_entry_id"] for d in draws}
    eligible_count = total_verified - len(already_won_ids)

    if eligible_count <= 0:
        raise HTTPException(
            status_code=409,
            detail="No eligible verified entries available for the draw. "
                   "All verified entries may have already won.",
        )

    try:
        result = db.draw_winner()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Draw failed: {e}")

    winner = result["winner"]
    draw = result["draw"]

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "draw_id": draw["id"],
            "drawn_at": draw["drawn_at"],
            "winner": {
                "entry_id": winner["id"],
                "name": winner["name"],
                "email": winner["email"],
                "phone": winner["phone"],
                "receipt_url": winner.get("receipt_url"),
                "created_at": winner["created_at"],
            },
            "eligible_entries": eligible_count,
        },
    )


@app.get("/api/admin/draws")
async def list_all_draws(
    x_admin_password: Optional[str] = Header(None),
):
    """List all previous raffle draws with winner details."""
    _check_admin_auth(x_admin_password)

    draws = db.list_draws()
    return JSONResponse(
        status_code=200,
        content={"draws": draws, "total": len(draws)},
    )
