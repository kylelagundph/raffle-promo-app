-- ============================================================
-- Raffle Promotion App — Supabase/PostgreSQL Schema v2
-- Run this in the Supabase SQL editor to initialize the database
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ENTRIES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS entries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                TEXT NOT NULL,
    email               TEXT NOT NULL,
    phone               TEXT NOT NULL,
    purchase_date       DATE,                          -- User-submitted purchase date
    invoice_number      TEXT,                          -- OR/POS number (10-digit, unique)
    receipt_url         TEXT,
    receipt_hash        TEXT,                          -- MD5 hash for duplicate image detection
    extracted_text      TEXT,                          -- Raw OCR text
    extracted_data      JSONB DEFAULT '{}',            -- Parsed receipt fields
    verification_status TEXT NOT NULL DEFAULT 'pending'
                            CHECK (verification_status IN ('pending', 'verified', 'rejected')),
    rejection_reason    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Invoice number must be unique (one entry per receipt)
CREATE UNIQUE INDEX IF NOT EXISTS entries_invoice_idx
    ON entries (LOWER(invoice_number))
    WHERE invoice_number IS NOT NULL AND invoice_number != '';

-- Duplicate image detection
CREATE UNIQUE INDEX IF NOT EXISTS entries_receipt_hash_idx
    ON entries (receipt_hash)
    WHERE receipt_hash IS NOT NULL;

-- NOTE: Multiple entries per email/phone are ALLOWED (unique receipt per entry)
-- So NO unique index on email or phone

CREATE INDEX IF NOT EXISTS entries_email_idx     ON entries (LOWER(email));
CREATE INDEX IF NOT EXISTS entries_phone_idx     ON entries (phone);
CREATE INDEX IF NOT EXISTS entries_status_idx    ON entries (verification_status);
CREATE INDEX IF NOT EXISTS entries_created_idx   ON entries (created_at DESC);

-- ============================================================
-- SETTINGS TABLE (admin-editable via dashboard)
-- ============================================================
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default settings
INSERT INTO settings (key, value) VALUES
    ('campaign_start_date',       '2026-05-01'),
    ('campaign_end_date',         '2026-08-31'),
    ('required_product_keywords', 'BLT'),
    ('prize_description',         'Trip to Korea for 2 — flights, hotel, tour + ₩250,000 pocket money'),
    ('promo_title',               'Win a Trip to Korea!'),
    ('draw_date',                 '2026-09-01')
ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- RAFFLE DRAWS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS raffle_draws (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    winner_entry_id UUID NOT NULL REFERENCES entries(id) ON DELETE RESTRICT,
    drawn_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    draw_notes      TEXT
);

CREATE INDEX IF NOT EXISTS raffle_draws_drawn_at_idx ON raffle_draws (drawn_at DESC);

-- ============================================================
-- AUTO-UPDATE updated_at TRIGGER
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER entries_updated_at
    BEFORE UPDATE ON entries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER settings_updated_at
    BEFORE UPDATE ON settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
