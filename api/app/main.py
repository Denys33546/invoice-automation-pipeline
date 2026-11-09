"""Invoice Extractor API: upload a PDF invoice, get its fields back as JSON."""

from fastapi import Depends, FastAPI, HTTPException, UploadFile

from app.config import SettingsDep
from app.extractor import extract_invoice_bytes
from app.schemas import InvoiceResult, to_result
from app.security import require_api_key

app = FastAPI(
    title="Invoice Extractor API",
    version="0.1.0",
    description="Extracts fields and item tables from PDF invoices and checks the numbers.",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/extract",
    response_model=InvoiceResult,
    dependencies=[Depends(require_api_key)],
    tags=["extraction"],
    summary="Extract data from one PDF invoice",
    responses={
        401: {"description": "Invalid or missing API key"},
        413: {"description": "File is too large"},
    },
)
def extract(file: UploadFile, settings: SettingsDep) -> InvoiceResult:
    """Always answers 200 for a readable upload: check `valid` and `warnings` in the body.

    An unreadable or suspicious PDF is a normal business outcome (`valid: false`),
    not an HTTP error.
    """
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    invoice = extract_invoice_bytes(data, file.filename or "upload.pdf", settings.max_pages)
    return to_result(invoice)
