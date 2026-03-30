"""
storage.py — Receipt file upload via Supabase Storage.
"""

import os
import hashlib
import mimetypes
import uuid
from typing import Tuple

from supabase import create_client, Client

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif"
}
MAX_FILE_SIZE_MB = 10
BUCKET_NAME = "receipts"

_client = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        _client = create_client(url, key)
    return _client


def compute_md5(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


def validate_file(filename: str, file_bytes: bytes, content_type: str) -> None:
    """Raise ValueError if the file is invalid."""
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE_MB} MB.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    guessed = mimetypes.guess_type(filename)[0] or ""

    allowed_exts = {"jpg", "jpeg", "png", "heic", "heif"}
    if ext not in allowed_exts and content_type not in ALLOWED_MIME_TYPES and guessed not in ALLOWED_MIME_TYPES:
        raise ValueError("Only JPG, PNG, or HEIC images are accepted.")


async def upload_receipt(
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> Tuple[str, str]:
    """
    Upload receipt image to Supabase Storage.
    Returns (public_url, storage_path).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    unique_name = f"{uuid.uuid4()}.{ext}"
    storage_path = f"receipts/{unique_name}"

    client = _get_client()
    client.storage.from_(BUCKET_NAME).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": content_type or "image/jpeg"},
    )

    # Get public URL
    url_resp = client.storage.from_(BUCKET_NAME).get_public_url(storage_path)
    public_url = url_resp if isinstance(url_resp, str) else url_resp.get("publicURL", storage_path)

    return public_url, storage_path
