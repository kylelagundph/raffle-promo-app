"""
local_server.py — Local development server with mock backends
Run: ../.venv/bin/python local_server.py
Then open: http://localhost:8000
"""

import os
import sys
import uuid
import hashlib
import json
from pathlib import Path
from datetime import datetime

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="Raffle App — Local Dev")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory store (local dev only) ─────────────────────────
entries_db = {}
draws_db   = []

# ── Serve frontend static files ───────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
async def index():
    return FileResponse(str(frontend_dir / "index.html"))

@app.get("/admin")
async def admin():
    return FileResponse(str(frontend_dir / "admin.html"))

@app.get("/style.css")
async def css():
    return FileResponse(str(frontend_dir / "style.css"), media_type="text/css")

@app.get("/app.js")
async def js():
    return FileResponse(str(frontend_dir / "app.js"), media_type="application/javascript")

# ── POST /api/submit ──────────────────────────────────────────
@app.post("/api/submit")
async def submit_entry(
    name: str    = Form(...),
    email: str   = Form(...),
    phone: str   = Form(...),
    consent: str = Form(default="true"),
    receipt: UploadFile = File(...),
):
    # Basic validation
    if not name or len(name.strip()) < 2:
        raise HTTPException(422, "Please enter your full name.")
    if "@" not in email:
        raise HTTPException(422, "Please enter a valid email address.")
    if len(phone.strip()) < 8:
        raise HTTPException(422, "Please enter a valid phone number.")
    if str(consent).lower() not in ("true", "1", "yes", "on"):
        raise HTTPException(422, "You must accept the terms to enter.")

    # Read file
    data = await receipt.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, "File too large. Maximum 10 MB.")

    allowed_types = {"image/jpeg", "image/png", "image/heic", "image/heif"}
    if receipt.content_type not in allowed_types and not (receipt.filename or "").lower().endswith((".jpg",".jpeg",".png",".heic",".heif")):
        raise HTTPException(422, "Only JPG, PNG, or HEIC files are accepted.")

    email = email.strip().lower()
    phone = phone.strip()

    # Dedup checks
    for e in entries_db.values():
        if e["email"] == email:
            raise HTTPException(409, "This email address has already been used to enter.")
        if e["phone"] == phone:
            raise HTTPException(409, "This phone number has already been used to enter.")

    receipt_hash = hashlib.md5(data).hexdigest()
    for e in entries_db.values():
        if e.get("receipt_hash") == receipt_hash:
            raise HTTPException(409, "This receipt has already been submitted.")

    entry_id = str(uuid.uuid4())

    # Mock OCR: simulate rejection — receipt does not contain required product
    keywords = [k.strip().lower() for k in os.getenv("REQUIRED_PRODUCT_KEYWORDS","test").split(",")]
    extracted_text = f"MOCK RECEIPT\nStore: Test Store\nDate: {datetime.now().strftime('%Y-%m-%d')}\nTransaction: TXN-{entry_id[:8].upper()}\nTotal: $12.50"
    status = "rejected"
    rejection_reason = "Not a valid receipt"

    entries_db[entry_id] = {
        "id": entry_id,
        "name": name.strip(),
        "email": email,
        "phone": phone,
        "receipt_url": f"/static/placeholder-receipt.png",
        "receipt_hash": receipt_hash,
        "extracted_text": extracted_text,
        "extracted_data": {
            "store_name": "Test Store",
            "purchase_date": datetime.now().strftime("%Y-%m-%d"),
            "transaction_number": f"TXN-{entry_id[:8].upper()}",
            "products": [keywords[0]],
        },
        "verification_status": status,
        "rejection_reason": rejection_reason,
        "created_at": datetime.now().isoformat(),
    }

    if status == "rejected":
        return JSONResponse(status_code=400, content={
            "success": False,
            "detail": rejection_reason,
            "entry_id": entry_id,
        })

    return JSONResponse(status_code=202, content={
        "success": True,
        "message": "Your entry has been received and verified!",
        "entry_id": entry_id,
    })


# ── POST /api/admin/login ─────────────────────────────────────
@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    pw   = body.get("password","")
    if pw != os.getenv("ADMIN_PASSWORD","admin123"):
        raise HTTPException(401, "Invalid password.")
    import jwt, time
    token = jwt.encode({"sub":"admin","exp": int(time.time()) + 3600}, "local-secret", algorithm="HS256")
    return {"token": token}


# ── GET /api/admin/entries ────────────────────────────────────
@app.get("/api/admin/entries")
async def admin_entries(request: Request):
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized.")
    return {"entries": list(entries_db.values())}


# ── POST /api/admin/draw ──────────────────────────────────────
@app.post("/api/admin/draw")
async def admin_draw(request: Request):
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized.")

    import random
    verified = [e for e in entries_db.values() if e["verification_status"] == "verified"]
    if not verified:
        raise HTTPException(400, "No verified entries to draw from.")

    num_winners = min(2, len(verified))
    winners = random.sample(verified, num_winners)
    for w in winners:
        draws_db.append({"winner_id": w["id"], "drawn_at": datetime.now().isoformat()})

    return {"success": True, "winner": winners[0], "winners": winners, "total_winners": num_winners}


if __name__ == "__main__":
    print("\n🎟️  Raffle App — Local Dev Server")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📋  Entry form:  http://localhost:8000")
    print("🔐  Admin panel: http://localhost:8000/admin")
    print(f"🔑  Admin pass:  {os.getenv('ADMIN_PASSWORD','admin123')}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    uvicorn.run("local_server:app", host="0.0.0.0", port=8000, reload=True)
