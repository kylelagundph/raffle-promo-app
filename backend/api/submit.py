"""
submit.py — POST /api/submit
"""

import os
import sys
import re
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from lib import db, storage, fraud

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "OPTIONS"], allow_headers=["*"])


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError(f"Invalid email: {email}")
    return email


def _validate_phone(phone: str) -> str:
    cleaned = phone.strip()
    digits = "".join(c for c in cleaned if c.isdigit())
    if len(digits) < 8 or len(digits) > 15:
        raise ValueError(f"Invalid phone: {phone}")
    return "+" + digits if cleaned.startswith("+") else digits


def _validate_invoice(invoice: str) -> str:
    invoice = invoice.strip()
    # Must be exactly 10 digits
    if not re.fullmatch(r"\d{10}", invoice):
        raise ValueError("Invoice/OR number must be exactly 10 digits.")
    return invoice


def _validate_purchase_date(date_str: str) -> str:
    """Validate date format YYYY-MM-DD."""
    import datetime
    date_str = date_str.strip()
    try:
        d = datetime.date.fromisoformat(date_str)
        # Check within promo period
        settings = db.get_settings()
        start = datetime.date.fromisoformat(settings.get("campaign_start_date", "2026-05-01"))
        end   = datetime.date.fromisoformat(settings.get("campaign_end_date",   "2026-08-31"))
        if d < start:
            raise ValueError(f"Purchase date is before the promo period (starts {start}).")
        if d > end:
            raise ValueError(f"Purchase date is after the promo period (ends {end}).")
        return date_str
    except ValueError as e:
        if "Invalid isoformat" in str(e):
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")
        raise


@app.post("/api/submit")
async def submit_entry(
    name:           str        = Form(...),
    email:          str        = Form(...),
    phone:          str        = Form(...),
    purchase_date:  str        = Form(...),
    invoice_number: str        = Form(...),
    consent:        str        = Form(...),
    receipt:        UploadFile = File(...),
):
    # 1. Validate fields
    name = name.strip()
    if not name or len(name) < 2:
        raise HTTPException(422, "Please enter your full name.")

    try:
        email = _validate_email(email)
    except ValueError as e:
        raise HTTPException(422, str(e))

    try:
        phone = _validate_phone(phone)
    except ValueError as e:
        raise HTTPException(422, str(e))

    try:
        purchase_date = _validate_purchase_date(purchase_date)
    except ValueError as e:
        raise HTTPException(422, str(e))

    try:
        invoice_number = _validate_invoice(invoice_number)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if str(consent).lower() not in ("true", "1", "yes", "on"):
        raise HTTPException(422, "You must accept the Terms & Conditions to enter.")

    # 2. Read and validate file
    receipt_bytes = await receipt.read()
    try:
        storage.validate_file(receipt.filename or "receipt.jpg", receipt_bytes, receipt.content_type or "")
    except ValueError as e:
        raise HTTPException(422, str(e))

    # 3. Check duplicate invoice number FIRST (fast check)
    try:
        fraud.check_duplicate_invoice(invoice_number)
    except fraud.FraudError as e:
        raise HTTPException(409, str(e))

    # 4. Compute MD5 hash for storage reference (no longer used for duplicate blocking)
    receipt_hash = storage.compute_md5(receipt_bytes)

    # 5. Upload receipt image to Supabase Storage
    try:
        receipt_url, _ = await storage.upload_receipt(
            receipt.filename or "receipt.jpg",
            receipt_bytes,
            receipt.content_type or "image/jpeg",
        )
    except Exception as e:
        raise HTTPException(500, f"File upload failed: {e}")

    # 6. Create entry in DB
    try:
        entry = db.create_entry(
            name=name,
            email=email,
            phone=phone,
            purchase_date=purchase_date,
            invoice_number=invoice_number,
            receipt_url=receipt_url,
            receipt_hash=receipt_hash,
        )
    except Exception as e:
        raise HTTPException(500, f"Database error: {e}")

    # 7. Run OCR verification inline and return result to user
    is_valid, rejection_reason = await _verify_and_update(entry["id"], receipt_bytes, purchase_date)

    if not is_valid:
        # Return rejection message directly to user
        user_message = "Entry is invalid — Promo Product not found."
        if rejection_reason and "date" in rejection_reason.lower():
            user_message = f"Entry is invalid — {rejection_reason}"
        elif rejection_reason and "read" in rejection_reason.lower():
            user_message = "Entry is invalid — Receipt image could not be read clearly. Please upload a clearer photo."
        return JSONResponse(status_code=422, content={
            "success": False,
            "message": user_message,
            "entry_id": entry["id"],
        })

    return JSONResponse(status_code=202, content={
        "success":  True,
        "message":  "You're in the draw! Good luck! 🇰🇷",
        "entry_id": entry["id"],
    })


async def _verify_and_update(entry_id: str, image_bytes: bytes, submitted_date: str):
    """Run OCR + verification inline. Returns (is_valid, rejection_reason)."""
    try:
        from lib.ocr import extract_text_from_image, parse_receipt, verify_receipt_with_settings

        raw_text = await extract_text_from_image(image_bytes)
        extracted_data = parse_receipt(raw_text)
        extracted_data["submitted_purchase_date"] = submitted_date

        is_valid, rejection_reason = await verify_receipt_with_settings(raw_text, extracted_data)

        db.update_entry_verification(
            entry_id=entry_id,
            status="verified" if is_valid else "rejected",
            extracted_text=raw_text,
            extracted_data=extracted_data,
            rejection_reason=rejection_reason,
        )
        return is_valid, rejection_reason
    except Exception as exc:
        db.update_entry_verification(
            entry_id=entry_id,
            status="pending",
            rejection_reason=f"Verification error (manual review needed): {exc}",
        )
        return True, None  # Don't block user on technical errors
