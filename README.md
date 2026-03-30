# 🎟️ Receipt-Based Raffle Promotion App

A full-stack web app for running receipt-based raffle promotions. Customers upload their purchase receipt, the system verifies it using Google Vision OCR, detects duplicates/fraud, and stores valid entries for a randomised raffle draw.

---

## Stack

| Layer       | Technology                          |
|-------------|-------------------------------------|
| Frontend    | Vanilla HTML / CSS / JS (mobile-first) |
| Backend     | Python FastAPI (Vercel serverless)  |
| Database    | PostgreSQL via Supabase             |
| OCR         | Google Vision API                   |
| File Storage| Vercel Blob                         |
| Hosting     | Vercel                              |

---

## Project Structure

```
raffle-app/
├── frontend/
│   ├── index.html      # Customer entry form
│   ├── admin.html      # Admin dashboard
│   ├── style.css       # Shared styles
│   └── app.js          # Frontend JS
├── backend/
│   ├── api/
│   │   ├── submit.py   # POST /api/submit
│   │   ├── verify.py   # POST /api/verify
│   │   ├── admin.py    # GET /api/admin/entries + POST /api/admin/login
│   │   └── draw.py     # POST /api/admin/draw
│   ├── lib/
│   │   ├── db.py       # Supabase client
│   │   ├── ocr.py      # Google Vision integration
│   │   ├── fraud.py    # Duplicate/fraud detection
│   │   └── storage.py  # Vercel Blob + file validation
│   └── requirements.txt
├── database/
│   └── schema.sql      # PostgreSQL schema (run in Supabase)
├── vercel.json         # Vercel deployment config
├── .env.example        # Environment variable template
└── README.md
```

---

## Setup Guide

### 1. Supabase (Database)

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project
3. Go to **SQL Editor** and run the contents of `database/schema.sql`
4. Go to **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role** key (not anon) → `SUPABASE_KEY`

### 2. Google Vision API (OCR)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Cloud Vision API**
4. Go to **APIs & Services → Credentials → Create Credentials → API Key**
5. Restrict the key to Cloud Vision API only
6. Copy the key → `GOOGLE_VISION_API_KEY`

### 3. Vercel Account & Blob Storage

1. Go to [vercel.com](https://vercel.com) and create a free account
2. In your dashboard, go to **Storage → Create → Blob Store**
3. Name it (e.g., `raffle-receipts`)
4. Copy the `BLOB_READ_WRITE_TOKEN` from the `.env.local` tab

### 4. Local Development

```bash
# Clone / navigate to project
cd raffle-app

# Copy env file
cp .env.example .env
# Fill in all values in .env

# Install Python dependencies
cd backend
pip install -r requirements.txt

# Run locally
uvicorn api.submit:app --reload --port 8000
```

Visit `http://localhost:8000` for the API, and open `frontend/index.html` directly in a browser for the form (or serve with `python3 -m http.server 3000` from the frontend folder).

### 5. Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# From the raffle-app root directory
vercel

# Follow prompts, then set environment variables:
vercel env add GOOGLE_VISION_API_KEY
vercel env add SUPABASE_URL
vercel env add SUPABASE_KEY
vercel env add BLOB_READ_WRITE_TOKEN
vercel env add ADMIN_PASSWORD
vercel env add CAMPAIGN_START_DATE
vercel env add CAMPAIGN_END_DATE
vercel env add REQUIRED_PRODUCT_KEYWORDS

# Deploy to production
vercel --prod
```

### 6. Connect a Custom Domain

1. In Vercel dashboard → your project → **Settings → Domains**
2. Click **Add Domain** and enter your domain (e.g., `promo.yourbrand.com`)
3. Vercel will show you DNS records to add at your registrar:
   - For an apex domain: add an **A record** pointing to Vercel's IP
   - For a subdomain: add a **CNAME record** pointing to `cname.vercel-dns.com`
4. Wait for DNS propagation (usually 5–30 minutes)
5. Vercel automatically provisions SSL

---

## Configuration

| Variable | Description |
|---|---|
| `GOOGLE_VISION_API_KEY` | Google Cloud Vision API key |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob storage token |
| `ADMIN_PASSWORD` | Password to access admin dashboard |
| `CAMPAIGN_START_DATE` | Campaign start date (YYYY-MM-DD) |
| `CAMPAIGN_END_DATE` | Campaign end date (YYYY-MM-DD) |
| `REQUIRED_PRODUCT_KEYWORDS` | Comma-separated product keywords to match on receipt |

---

## Fraud & Duplicate Detection

The system checks for:
- **Duplicate email** — one entry per email address
- **Duplicate phone** — one entry per phone number
- **Duplicate receipt** — MD5 hash comparison of the image file
- **Duplicate transaction number** — extracted from OCR text
- **Date out of range** — purchase date must be within campaign period
- **Product not found** — required product keywords must appear in OCR text

---

## Admin Dashboard

Access at `/admin` or `/admin.html`

Features:
- Password-protected login
- Entry stats (total / pending / verified / rejected)
- Filter entries by status
- View receipt images
- See extracted OCR text per entry
- Run a randomised raffle draw
- Export all entries as CSV

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/submit` | Submit an entry with receipt image |
| `POST` | `/api/verify` | Manually trigger verification for an entry |
| `POST` | `/api/admin/login` | Admin login, returns JWT token |
| `GET` | `/api/admin/entries` | List all entries (auth required) |
| `POST` | `/api/admin/draw` | Run raffle draw (auth required) |

---

## Scaling Notes

- Supabase free tier handles ~500MB DB and 2GB bandwidth — sufficient for ~50,000 entries with receipt images stored in Vercel Blob (not the DB)
- Vercel free tier: 100GB bandwidth, unlimited serverless function invocations on Hobby plan
- For very high traffic spikes (e.g., flash campaigns), consider upgrading to Vercel Pro for increased concurrency limits
- Google Vision API free tier: 1,000 requests/month. At 50k entries, estimate ~$75–150 in Vision API costs (currently $1.50/1000 requests)

---

## License

MIT
