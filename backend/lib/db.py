"""
db.py — Supabase (PostgreSQL) client and data access layer.
"""

import os
from typing import Any, Dict, List, Optional
from supabase import create_client, Client

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if url == "mock" or key == "mock":
            raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
        _client = create_client(url, key)
    return _client


# ------------------------------------------------------------------ #
#  Settings
# ------------------------------------------------------------------ #

def get_settings() -> Dict[str, str]:
    """Load all settings from DB. Falls back to env vars if DB not available."""
    try:
        client = get_client()
        resp = client.table("settings").select("key,value").execute()
        return {row["key"]: row["value"] for row in (resp.data or [])}
    except Exception:
        return {
            "campaign_start_date":       os.environ.get("CAMPAIGN_START_DATE", "2026-05-01"),
            "campaign_end_date":         os.environ.get("CAMPAIGN_END_DATE", "2026-08-31"),
            "required_product_keywords": os.environ.get("REQUIRED_PRODUCT_KEYWORDS", "BLT"),
            "prize_description":         os.environ.get("PRIZE_DESCRIPTION", "Trip to Korea for 2"),
            "promo_title":               os.environ.get("PROMO_TITLE", "Win a Trip to Korea!"),
            "draw_date":                 os.environ.get("DRAW_DATE", "2026-09-01"),
        }


def update_setting(key: str, value: str) -> None:
    client = get_client()
    client.table("settings").upsert({"key": key, "value": value}).execute()


# ------------------------------------------------------------------ #
#  Entries
# ------------------------------------------------------------------ #

def create_entry(
    name: str,
    email: str,
    phone: str,
    purchase_date: Optional[str],
    invoice_number: str,
    receipt_url: str,
    receipt_hash: str,
) -> Dict[str, Any]:
    client = get_client()
    resp = client.table("entries").insert({
        "name":           name,
        "email":          email,
        "phone":          phone,
        "purchase_date":  purchase_date,
        "invoice_number": invoice_number.strip() if invoice_number else None,
        "receipt_url":    receipt_url,
        "receipt_hash":   receipt_hash,
        "verification_status": "pending",
    }).execute()

    if not resp.data:
        raise RuntimeError("Failed to create entry.")
    return resp.data[0]


def update_entry_verification(
    entry_id: str,
    status: str,
    extracted_text: str = "",
    extracted_data: Optional[Dict] = None,
    rejection_reason: Optional[str] = None,
) -> None:
    client = get_client()
    client.table("entries").update({
        "verification_status": status,
        "extracted_text":      extracted_text,
        "extracted_data":      extracted_data or {},
        "rejection_reason":    rejection_reason,
    }).eq("id", entry_id).execute()


def delete_entry(entry_id: str) -> bool:
    """
    Permanently delete an entry by ID regardless of verification status.
    Nullifies any raffle_draws references first to avoid FK constraint errors.
    Returns True if deleted, False if not found.
    """
    client = get_client()

    # Check entry exists
    check = client.table("entries").select("id").eq("id", entry_id).limit(1).execute()
    if not check.data:
        return False

    # Nullify winner_entry_id in raffle_draws if this entry was ever a draw winner
    # (handles both RESTRICT and SET NULL FK constraints)
    try:
        client.table("raffle_draws").update({"winner_entry_id": None}).eq("winner_entry_id", entry_id).execute()
    except Exception:
        pass  # If already SET NULL on FK, this is a no-op

    # Now delete the entry
    client.table("entries").delete().eq("id", entry_id).execute()
    return True


def get_entries(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    client = get_client()
    query = client.table("entries").select(
        "id,name,email,phone,purchase_date,invoice_number,"
        "receipt_url,verification_status,rejection_reason,created_at"
    ).order("created_at", desc=True).limit(limit).offset(offset)

    if status:
        query = query.eq("verification_status", status)

    resp = query.execute()
    return resp.data or []


def count_entries(status: Optional[str] = None) -> int:
    client = get_client()
    query = client.table("entries").select("id", count="exact")
    if status:
        query = query.eq("verification_status", status)
    resp = query.execute()
    return resp.count or 0


def get_verified_entries_for_draw() -> List[Dict[str, Any]]:
    """Return all verified entries eligible for raffle draw."""
    client = get_client()
    resp = client.table("entries").select(
        "id,name,email,phone,invoice_number,created_at"
    ).eq("verification_status", "verified").execute()
    return resp.data or []


def check_invoice_exists(invoice_number: str) -> bool:
    client = get_client()
    resp = client.table("entries").select("id").ilike(
        "invoice_number", invoice_number.strip()
    ).limit(1).execute()
    return bool(resp.data)


def check_receipt_hash_exists(receipt_hash: str) -> bool:
    client = get_client()
    resp = client.table("entries").select("id").eq(
        "receipt_hash", receipt_hash
    ).limit(1).execute()
    return bool(resp.data)


# ------------------------------------------------------------------ #
#  Raffle Draw
# ------------------------------------------------------------------ #

def record_draw(winner_entry_id: str, notes: str = "") -> Dict[str, Any]:
    client = get_client()
    resp = client.table("raffle_draws").insert({
        "winner_entry_id": winner_entry_id,
        "draw_notes":      notes,
    }).execute()
    if not resp.data:
        raise RuntimeError("Failed to record draw.")
    return resp.data[0]


def get_draws() -> List[Dict[str, Any]]:
    client = get_client()
    resp = client.table("raffle_draws").select(
        "id,drawn_at,draw_notes,entries(name,email,phone,invoice_number)"
    ).order("drawn_at", desc=True).execute()
    return resp.data or []
