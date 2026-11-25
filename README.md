# Invoice Automation Pipeline

[![CI](https://github.com/Denys33546/invoice-automation-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Denys33546/invoice-automation-pipeline/actions/workflows/ci.yml)

Reads PDF invoices, checks that the numbers add up, and sends problem invoices to a person for review.

An **n8n** workflow receives the invoice, a **FastAPI** service extracts the data and validates the math, and the workflow decides what happens next:

- **Valid invoice** → the pipeline answers `processed`.
- **Problem found** (wrong total, missing date, unreadable file…) → an email with the list of problems goes to the accountant, and the pipeline answers `needs_review`.

Everything runs locally with one command through Docker Compose.

## How it works

```
PDF invoice
    │  POST /webhook/invoices
    ▼
┌─────────┐   POST /extract    ┌──────────────────┐
│  n8n    │ ─────────────────► │  Extractor API   │
│workflow │ ◄───────────────── │  (FastAPI)       │
└────┬────┘   JSON + warnings  └──────────────────┘
     │
     ├── valid   → respond "processed"
     └── invalid → email the accountant (Mailpit) → respond "needs_review"
```

The extractor pulls out the invoice number, date, vendor, customer, line items, subtotal, tax and total. Then it checks:

- quantity × unit price = line amount, for every line;
- sum of the lines = subtotal;
- subtotal + tax = total.

Money is handled with `Decimal` (no floating-point errors) and returned as strings with two decimals, for example `"84.24"`.

## Tech stack

| Part | Technology |
|---|---|
| Extractor API | Python 3.12, FastAPI, pdfplumber, pydantic |
| Workflow | n8n |
| Test mail server | Mailpit |
| Packaging | Docker, Docker Compose |
| Quality | pytest (28 tests), ruff, GitHub Actions |

## Quick start

You need [Docker](https://docs.docker.com/get-docker/) with Docker Compose.

**1. Clone and create the settings file**

```bash
git clone https://github.com/Denys33546/invoice-automation-pipeline.git
cd invoice-automation-pipeline
cp .env.example .env
```

**2. Put real secrets into `.env`**

```bash
openssl rand -hex 32   # use the output as EXTRACTOR_API_KEY
openssl rand -hex 32   # use the output as N8N_ENCRYPTION_KEY
```

Keep `N8N_ENCRYPTION_KEY`: without it the credentials saved inside n8n are lost.

**3. Start everything**

```bash
docker compose up -d --build
```

| Service | Address |
|---|---|
| Extractor API (interactive docs) | http://localhost:8010/docs |
| n8n | http://localhost:5678 |
| Mailpit (caught emails) | http://localhost:8025 |

All ports are bound to `127.0.0.1`, so nothing is exposed to your network.

## Try the extractor API directly

```bash
curl -X POST http://localhost:8010/extract \
  -H "X-API-Key: <your EXTRACTOR_API_KEY>" \
  -F "file=@samples/invoice_0001.pdf"
```

Response for a correct invoice:

```json
{
  "source": "invoice_0001.pdf",
  "valid": true,
  "number": "INV-2026-0001",
  "issue_date": "2026-03-03",
  "vendor": "Blue Harbor Trading",
  "customer": "Sample Customer Inc.",
  "items": [
    { "description": "USB-C cable 1 m", "quantity": 5, "unit_price": "4.99", "amount": "24.95" },
    { "description": "HDMI adapter", "quantity": 4, "unit_price": "12.40", "amount": "49.60" }
  ],
  "subtotal": "74.55",
  "tax": "9.69",
  "total": "84.24",
  "warnings": []
}
```

A problem invoice is **not** an HTTP error. The API answers `200` with `"valid": false` and explains what is wrong:

```json
{
  "source": "problem_wrong_total.pdf",
  "valid": false,
  "number": "INV-9001",
  "total": "99.00",
  "warnings": ["Subtotal + tax is 22.60, but the total is 99.00"]
}
```

(Other fields are shortened here.) The API answers `401` for a wrong or missing API key and `413` for a file over the size limit.

## Run the full pipeline in n8n

**1. Import the workflow.** In n8n choose *Workflows → Import from file* and select `n8n/workflows/invoice_pipeline.json`.

**2. Create two credentials:**

- **Extractor API key** (type *Header Auth*): name `X-API-Key`, value = `EXTRACTOR_API_KEY` from your `.env`.
- **Mailpit** (type *SMTP*): host `mailpit`, port `1025`, any user and password, SSL off.

**3. Activate the workflow, then send an invoice:**

```bash
curl -X POST http://localhost:5678/webhook/invoices \
  -F "file=@samples/invoice_0001.pdf"
```

A valid invoice returns `processed`. To see the review path, send one of the invoices with a deliberate problem:

```bash
curl -X POST http://localhost:5678/webhook/invoices \
  -F "file=@n8n/workflows/problem_wrong_total.pdf"
```

The answer is `needs_review`, and the email with the list of problems appears in Mailpit at http://localhost:8025.

## Settings

Variables read by the API (prefix `EXTRACTOR_`):

| Variable | Default | Meaning |
|---|---|---|
| `EXTRACTOR_API_KEY` | empty | Key required in the `X-API-Key` header. Empty means authentication is off. Docker Compose requires it to be set. |
| `EXTRACTOR_MAX_UPLOAD_MB` | `10` | Maximum upload size. |
| `EXTRACTOR_MAX_PAGES` | `20` | Maximum number of pages per PDF. |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check api
ruff format --check api
pytest --cov=api/app
```

The same checks run in GitHub Actions on every push and pull request, together with a validation of the n8n workflow JSON and a Docker image build.

## Limitations

- Works with **text-based PDFs**. Scanned documents (images) are not supported; there is no OCR, and the API reports this clearly.
- The parser expects a specific invoice layout: an item table with the header `Description / Qty / Unit Price / Amount`, a date in `YYYY-MM-DD` format, and a `Bill To:` line. Other layouts need small changes to the patterns in `api/app/extractor.py`.
- The email step uses Mailpit, a local test inbox. For real use, replace it with your SMTP server in the n8n credentials.
- Meant to run locally or behind your own HTTPS. `N8N_SECURE_COOKIE=false` in `docker-compose.yml` is for local HTTP only; remove it behind HTTPS.

## Project structure

```
api/                    FastAPI extractor (app/, tests/, Dockerfile)
n8n/workflows/          n8n workflow and invoices with deliberate problems
samples/                sample valid invoices
scripts/                helper script that generates problem invoices
docker-compose.yml      api + n8n + Mailpit
.github/workflows/      CI
```

## Need this for your invoices?

I adapt the pipeline to your invoice layouts and connect it to your tools (email, Google Sheets, accounting software). Contact me: _add your LinkedIn or email here_.

## License

_Add a license (for example MIT) and a `LICENSE` file._
