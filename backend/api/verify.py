"""
verify.py — POST /api/verify
Manually trigger OCR + verification for a specific entry by entry_id.
Useful for re-processing pending entries or retrying failed OCR.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

from lib import db, fraud
from lib.ocr import extract_text_from_image, parse_receipt, verify_receipt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


def _require_admin(x_admin_password: str = None):
    """Simple shared-secret admin check via header."""
    import os
    from fastapi import Header
    return x_admin_password


def _check_admin_auth(request_password: str) -> None:
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_password or request_password != admin_password:
        raise HTTPException(status_code=401, detail="Unauthorized")


class VerifyRequest(BaseModel):
    entry_id: str
    admin_password: str


@app.post("/api/verify")
async def verify_entry(body: VerifyRequest):
    _check_admin_auth(body.admin_password)

    # Fetch the entry
    entry = db.get_entry_by_id(body.entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found.")

    if not entry.get("receipt_url"):
        raise HTTPException(status_code=422, detail="Entry has no receipt URL to process.")

    # Download the receipt image from Vercel Blob
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            img_response = await client.get(entry["receipt_url"])
        img_response.raise_for_status()
        image_bytes = img_response.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not download receipt image: {e}")

    # Run OCR
    try:
        raw_text = await extract_text_from_image(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OCR failed: {e}")

    extracted_data = parse_receipt(raw_text)

    # Post-OCR fraud check: transaction number dedup
    txn_number = extracted_data.get("transaction_number")
    if txn_number:
        existing = db.get_entry_by_transaction_number(txn_number)
        if existing and existing["id"] != body.entry_id:
            updated = db.update_entry_verification(
                entry_id=body.entry_id,
                status="rejected",
                extracted_text=raw_text,
                extracted_data=extracted_data,
                rejection_reason=(
                    f"Duplicate transaction number: {txn_number} already used by entry {existing['id']}."
                ),
            )
            return JSONResponse(
                status_code=200,
                content={
                    "entry_id": body.entry_id,
                    "status": "rejected",
                    "reason": updated["rejection_reason"],
                    "extracted_data": extracted_data,
                },
            )

    # Verify receipt meets campaign requirements
    is_valid, rejection_reason = verify_receipt(raw_text, extracted_data)

    updated = db.update_entry_verification(
        entry_id=body.entry_id,
        status="verified" if is_valid else "rejected",
        extracted_text=raw_text,
        extracted_data=extracted_data,
        rejection_reason=rejection_reason,
    )

    return JSONResponse(
        status_code=200,
        content={
            "entry_id": body.entry_id,
            "status": updated["verification_status"],
            "reason": rejection_reason,
            "extracted_data": extracted_data,
            "raw_text_preview": raw_text[:500] if raw_text else "",
        },
    )
