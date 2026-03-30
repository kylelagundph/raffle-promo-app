"""
fraud.py — Duplicate and fraud detection logic.
"""

from typing import Optional
from . import db


class FraudError(Exception):
    """Raised when a fraud/duplicate check fails."""


def check_duplicate_invoice(invoice_number: str) -> None:
    """Raise FraudError if this invoice/OR number has already been submitted."""
    if not invoice_number or not invoice_number.strip():
        raise FraudError("Invoice/OR number is required.")
    if db.check_invoice_exists(invoice_number.strip()):
        raise FraudError(
            f"Invoice number {invoice_number} has already been submitted. "
            "Each entry must use a unique receipt."
        )


def check_duplicate_receipt_image(receipt_hash: str) -> None:
    """Raise FraudError if the same receipt image has been uploaded before."""
    if db.check_receipt_hash_exists(receipt_hash):
        raise FraudError(
            "This receipt image has already been submitted. "
            "Please upload a different receipt."
        )
