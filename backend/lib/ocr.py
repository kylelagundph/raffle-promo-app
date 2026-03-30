"""
ocr.py — Google Vision API integration for receipt text extraction and parsing.
"""

import os
import base64
import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx


# ------------------------------------------------------------------ #
#  Vision API call
# ------------------------------------------------------------------ #

async def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Call Google Vision API TEXT_DETECTION on the provided image bytes.
    Returns the full raw text as a single string.
    """
    api_key = os.environ.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_VISION_API_KEY environment variable is not set.")

    encoded = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "requests": [
            {
                "image": {"content": encoded},
                "features": [
                    {"type": "TEXT_DETECTION", "maxResults": 1},
                    {"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1},
                ],
            }
        ]
    }

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)

    if response.status_code != 200:
        raise RuntimeError(
            f"Google Vision API error {response.status_code}: {response.text}"
        )

    result = response.json()

    try:
        # Prefer DOCUMENT_TEXT_DETECTION full text
        full_text = (
            result["responses"][0]
            .get("fullTextAnnotation", {})
            .get("text", "")
        )
        if not full_text:
            # Fall back to TEXT_DETECTION
            full_text = (
                result["responses"][0]
                .get("textAnnotations", [{}])[0]
                .get("description", "")
            )
        return full_text.strip()
    except (KeyError, IndexError):
        return ""


# ------------------------------------------------------------------ #
#  Receipt parsing helpers
# ------------------------------------------------------------------ #

DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b",
    # YYYY-MM-DD
    r"\b(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})\b",
    # DD MMM YYYY or DD MMMM YYYY
    r"\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{4})\b",
]

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

TXN_PATTERNS = [
    r"(?:transaction|txn|receipt|order|ref(?:erence)?|invoice|inv)[^\w]*(?:no|num|number|#|id)?[^\w]*[:.\s]*([A-Z0-9\-]{4,30})",
    r"(?:receipt|invoice)\s*#?\s*([A-Z0-9\-]{4,20})",
    r"#\s*([A-Z0-9\-]{6,20})",
]


def _parse_date(text: str) -> Optional[str]:
    """Try to extract the purchase date from raw OCR text. Returns ISO date string or None."""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 3:
                    g1, g2, g3 = groups
                    # YYYY-MM-DD
                    if len(g1) == 4:
                        return date(int(g1), int(g2), int(g3)).isoformat()
                    # DD MMM YYYY
                    if not g2.isdigit():
                        month = MONTH_MAP.get(g2.lower())
                        if month:
                            return date(int(g3), month, int(g1)).isoformat()
                    # DD/MM/YYYY
                    return date(int(g3), int(g2), int(g1)).isoformat()
            except ValueError:
                continue
    return None


def _parse_transaction_number(text: str) -> Optional[str]:
    """Try to extract a transaction/receipt number from raw OCR text."""
    for pattern in TXN_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn = match.group(1).strip().upper()
            if len(txn) >= 4:
                return txn
    return None


def _parse_store_name(text: str) -> Optional[str]:
    """
    Attempt to extract the store name — typically the first non-empty line of a receipt.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        # Skip very short lines (single chars) and lines that look purely numeric
        for line in lines[:5]:
            if len(line) >= 3 and not re.fullmatch(r"[\d\s\W]+", line):
                return line
    return None


def _parse_line_items(text: str) -> List[str]:
    """
    Heuristically extract product line items from receipt text.
    Looks for lines that end with a price pattern.
    """
    price_pattern = re.compile(r"\$?\d+[\.,]\d{2}\s*$")
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if price_pattern.search(stripped) and len(stripped) > 5:
            # Remove the trailing price
            item_name = price_pattern.sub("", stripped).strip()
            if item_name:
                items.append(item_name)
    return items[:20]  # cap at 20 items


def _parse_total_amount(text: str) -> Optional[str]:
    """Extract total/grand total amount."""
    pattern = re.compile(
        r"(?:total|grand\s+total|amount\s+due|balance\s+due)[^\d]*(\$?\s*\d+[\.,]\d{2})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        return match.group(1).replace(" ", "")
    return None


def parse_receipt(raw_text: str) -> Dict[str, Any]:
    """
    Parse the raw OCR text into structured fields.
    Returns a dict with keys: store_name, purchase_date, transaction_number,
    line_items, total_amount.
    """
    return {
        "store_name": _parse_store_name(raw_text),
        "purchase_date": _parse_date(raw_text),
        "transaction_number": _parse_transaction_number(raw_text),
        "line_items": _parse_line_items(raw_text),
        "total_amount": _parse_total_amount(raw_text),
    }


# ------------------------------------------------------------------ #
#  Verification logic
# ------------------------------------------------------------------ #

def get_required_keywords() -> List[str]:
    raw = os.environ.get("REQUIRED_PRODUCT_KEYWORDS", "")
    return [kw.strip().lower() for kw in raw.split(",") if kw.strip()]


def get_campaign_dates() -> Tuple[Optional[date], Optional[date]]:
    start_str = os.environ.get("CAMPAIGN_START_DATE", "")
    end_str = os.environ.get("CAMPAIGN_END_DATE", "")
    start = None
    end = None
    try:
        if start_str:
            start = date.fromisoformat(start_str)
    except ValueError:
        pass
    try:
        if end_str:
            end = date.fromisoformat(end_str)
    except ValueError:
        pass
    return start, end


def verify_receipt(
    raw_text: str,
    extracted_data: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check that the receipt meets campaign requirements.
    Returns (is_valid, rejection_reason).
    """
    text_lower = raw_text.lower()

    # 1. Check required product keywords
    required_keywords = get_required_keywords()
    if required_keywords:
        missing = [kw for kw in required_keywords if kw not in text_lower]
        if missing:
            return False, (
                f"Receipt does not contain required product(s): "
                f"{', '.join(kw.title() for kw in missing)}."
            )

    # 2. Check purchase date within campaign window
    campaign_start, campaign_end = get_campaign_dates()
    purchase_date_str = extracted_data.get("purchase_date")

    if campaign_start or campaign_end:
        if not purchase_date_str:
            return False, "Could not detect a purchase date on the receipt."
        try:
            purchase_date = date.fromisoformat(purchase_date_str)
        except ValueError:
            return False, f"Invalid purchase date format: {purchase_date_str}"

        if campaign_start and purchase_date < campaign_start:
            return False, (
                f"Purchase date {purchase_date.isoformat()} is before the campaign "
                f"start date {campaign_start.isoformat()}."
            )
        if campaign_end and purchase_date > campaign_end:
            return False, (
                f"Purchase date {purchase_date.isoformat()} is after the campaign "
                f"end date {campaign_end.isoformat()}."
            )

    # 3. Basic sanity: ensure we got some text at all
    if len(raw_text.strip()) < 20:
        return False, "Receipt image could not be read clearly. Please upload a clearer photo."

    return True, None


async def verify_receipt_with_settings(
    raw_text: str,
    extracted_data: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Verify receipt using settings loaded from DB (admin-configurable).
    Falls back to env vars if DB unavailable.
    """
    from . import db as db_module
    settings = db_module.get_settings()

    text_lower = raw_text.lower()

    # 1. Check required product keywords (from DB settings)
    keywords_raw = settings.get("required_product_keywords", "")
    required_keywords = [k.strip().lower() for k in keywords_raw.split(",") if k.strip()]

    if required_keywords:
        missing = [kw for kw in required_keywords if kw not in text_lower]
        if missing:
            return False, (
                f"Receipt does not contain required product(s): "
                f"{', '.join(kw.title() for kw in missing)}."
            )

    # 2. Date check — use submitted date (user-entered), OCR date is cross-reference
    campaign_start_str = settings.get("campaign_start_date", "")
    campaign_end_str   = settings.get("campaign_end_date", "")
    submitted_date_str = extracted_data.get("submitted_purchase_date", "")

    if campaign_start_str and campaign_end_str and submitted_date_str:
        try:
            purchase_date  = date.fromisoformat(submitted_date_str)
            campaign_start = date.fromisoformat(campaign_start_str)
            campaign_end   = date.fromisoformat(campaign_end_str)

            if purchase_date < campaign_start:
                return False, f"Purchase date {submitted_date_str} is before the promo period."
            if purchase_date > campaign_end:
                return False, f"Purchase date {submitted_date_str} is after the promo period."
        except ValueError:
            pass

    # 3. Basic sanity check
    if len(raw_text.strip()) < 20:
        return False, "Receipt image could not be read clearly. Please upload a clearer photo."

    return True, None
