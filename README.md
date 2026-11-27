# Invoice Automation Pipeline

[![CI](https://github.com/Denys33546/invoice-automation-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Denys33546/invoice-automation-pipeline/actions/workflows/ci.yml)

A local invoice-processing example built with **n8n** and **FastAPI**. Submit a PDF to the n8n webhook; the API extracts invoice fields and checks the arithmetic. Valid invoices return `processed`. Invoices with missing or inconsistent data return `needs_review` and trigger an email to the configured reviewer. The default local setup catches those emails in Mailpit.

## How it works

```text
PDF → n8n webhook → FastAPI extractor
                         ├─ valid   → processed
                         └─ problem → email via Mailpit → needs_review
```

The extractor reads the invoice number, date, vendor, customer, line items, subtotal, tax, and total. It checks quantity × unit price for each line, the sum of line amounts against the subtotal, and subtotal + tax against the total. Amounts use `Decimal` and are returned as strings with two decimal places.

## Requirements

- Docker with the Docker Compose plugin (`docker compose`)
- Open ports on localhost: `8010`, `5678`, and `8025`

## Quick start

Clone the repository and create a local environment file:

```bash
git clone https://github.com/Denys33546/invoice-automation-pipeline.git
cd invoice-automation-pipeline
cp .env.example .env
```

Generate two secrets and replace the placeholder values in `.env`:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Use one value for `EXTRACTOR_API_KEY` and the other for `N8N_ENCRYPTION_KEY`. Keep the encryption key: n8n uses it to protect saved credentials, and changing or losing it can make those credentials unusable.

Start the services:

```bash
docker compose up -d --build
```

| Service | Local address |
|---|---|
| Extractor API docs | http://localhost:8010/docs |
| n8n | http://localhost:5678 |
| Mailpit inbox | http://localhost:8025 |

Compose binds these ports to `127.0.0.1`. The n8n workflow is inactive until imported and activated.

To stop the services, run `docker compose down`. The n8n data volume is retained; add `-v` only if you also want to delete that saved data.

## Call the extractor API

The API accepts a multipart form field named `file` at `/extract`. With the Compose setup, provide the API key from `.env`:

```bash
curl -X POST http://localhost:8010/extract \
  -H "X-API-Key: <EXTRACTOR_API_KEY>" \
  -F "file=@samples/invoice_0001.pdf"
```

A valid sample returns fields like these:

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

Invoice problems are returned in a normal `200` response with `valid: false` and explanatory `warnings`; they are not HTTP errors. A missing or incorrect key returns `401`, and an upload over the configured size limit returns `413`. `/health` is public and returns `{"status":"ok"}`.

## Run the n8n workflow

1. Open n8n at http://localhost:5678 and complete its initial setup if prompted.
2. Import `n8n/workflows/invoice_pipeline.json` using **Workflows → Import from file**.
3. Create the credentials referenced by the workflow:
   - **Header Auth**: header name `X-API-Key`, value set to `EXTRACTOR_API_KEY` from `.env`.
   - **SMTP**: host `mailpit`, port `1025`, any username and password, SSL disabled.
4. Save and activate the workflow.

Send a valid invoice to the active webhook:

```bash
curl -X POST http://localhost:5678/webhook/invoices \
  -F "file=@samples/invoice_0001.pdf"
```

The response has `status: "processed"`. To exercise the review branch, send a sample with an incorrect total:

```bash
curl -X POST http://localhost:5678/webhook/invoices \
  -F "file=@samples/problem_wrong_total.pdf"
```

This returns `status: "needs_review"`; the workflow sends a message that can be viewed in Mailpit at http://localhost:8025. The sample with the missing date is `samples/problem_missing_date.pdf`; a non-PDF test file is `samples/problem_not_a_pdf.pdf`.

## Configuration

The API reads environment variables with the `EXTRACTOR_` prefix. The Compose file passes `EXTRACTOR_API_KEY` and requires it to be set. The other variables below have application defaults; the Compose file does not currently forward overrides for them.

| Variable | Default | Description |
|---|---:|---|
| `EXTRACTOR_API_KEY` | empty | Required key for the `X-API-Key` header when set. An empty key disables API-key checking. Compose requires a non-empty value. |
| `EXTRACTOR_MAX_UPLOAD_MB` | `10` | Maximum upload size in MiB. |
| `EXTRACTOR_MAX_PAGES` | `20` | Maximum PDF page count. |

## Development

The API requires Python 3.12. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --app-dir api --reload
```

The local API listens on port `8000`. To enable API-key checking, set `EXTRACTOR_API_KEY` in the shell before starting it. Run the quality checks with:

```bash
ruff check api
ruff format --check api
pytest --cov=api/app
```

For an already running API, `scripts/smoke_test.sh` checks health and sample extraction. It accepts an optional base URL and API key; for example, `scripts/smoke_test.sh http://localhost:8010 YOUR_API_KEY`.

GitHub Actions runs Ruff, formatting checks, pytest with coverage, JSON parsing of the n8n workflow, and a Docker image build on pushes to `main` and pull requests targeting `main`.

## Supported invoice format

- The parser handles text-based PDFs. Scanned/image-only PDFs are not OCR processed and are reported with a warning.
- The supported layout uses an item table with the columns `Description`, `Qty`, `Unit Price`, and `Amount`; a date in `YYYY-MM-DD` format; and a `Bill To:` line.
- The parser expects the invoice number, subtotal, tax, and total labels/layouts implemented in `api/app/extractor.py`. Other formats may need parser changes.
- Mailpit is a local test inbox. For real email delivery, configure the n8n SMTP credential to use an appropriate mail server.
- Compose sets `N8N_SECURE_COOKIE=false` for local HTTP. The configuration must be adjusted when deploying behind HTTPS.

## Project layout

```text
api/app/                    FastAPI routes, settings, parsing, and response models
api/tests/                  API and settings tests
n8n/workflows/              Importable workflow and problem invoice samples
n8n/checks/                 Workflow validation script and its Node dependencies
samples/                    Example invoices for API and workflow requests
scripts/                    Sample generator and API smoke test
.github/workflows/ci.yml    GitHub Actions checks
docker-compose.yml          API, n8n, and Mailpit services
```

## License

This repository does not currently contain a `LICENSE` file, so its reuse and distribution terms are unspecified.
