import pytest

from tests.pdfs import build_blank_pdf, build_invoice_pdf, build_text_pdf


def post_pdf(client, data, filename="invoice.pdf", **kwargs):
    return client.post("/extract", files={"file": (filename, data, "application/pdf")}, **kwargs)


# ---------- health ----------


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# ---------- a good invoice ----------


def test_valid_invoice_is_extracted(client):
    response = post_pdf(client, build_invoice_pdf(), "acme_9.pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["warnings"] == []
    assert body["source"] == "acme_9.pdf"
    assert body["number"] == "INV-9"
    assert body["issue_date"] == "2026-02-01"
    assert body["vendor"] == "Acme Parts"
    assert body["customer"] == "Buyer Ltd"
    assert body["subtotal"] == "20.00"
    assert body["tax"] == "2.60"
    assert body["total"] == "22.60"
    assert body["items"] == [
        {"description": "Widget", "quantity": 2, "unit_price": "10.00", "amount": "20.00"}
    ]


def test_amounts_are_json_strings_with_two_decimals(client):
    raw = post_pdf(client, build_invoice_pdf(total="$22.60")).text
    assert '"total":"22.60"' in raw.replace(" ", "")


def test_thousands_separator(client):
    pdf = build_invoice_pdf(
        items=[("Server", "1", "$1,000.00", "$1,000.00")],
        subtotal="$1,000.00",
        tax="$130.00",
        total="$1,130.00",
    )
    body = post_pdf(client, pdf).json()
    assert body["valid"] is True
    assert body["total"] == "1130.00"


# ---------- numbers that do not add up ----------


def test_wrong_total_is_flagged(client):
    body = post_pdf(client, build_invoice_pdf(total="$99.00")).json()
    assert body["valid"] is False
    assert any("Subtotal + tax" in warning for warning in body["warnings"])
    assert body["total"] == "99.00"  # the data is still returned


def test_wrong_subtotal_is_flagged(client):
    body = post_pdf(client, build_invoice_pdf(subtotal="$25.00")).json()
    assert any("Items add up" in warning for warning in body["warnings"])


def test_wrong_line_amount_is_flagged(client):
    pdf = build_invoice_pdf(items=[("Widget", "2", "$10.00", "$21.00")])
    body = post_pdf(client, pdf).json()
    assert any("Line 'Widget'" in warning for warning in body["warnings"])


# ---------- missing or odd content ----------


def test_missing_fields_are_flagged(client):
    pdf = build_invoice_pdf(number=None, issue_date=None, total=None)
    body = post_pdf(client, pdf).json()
    assert body["valid"] is False
    assert body["number"] is None and body["issue_date"] is None and body["total"] is None
    warnings = " | ".join(body["warnings"])
    assert "Invoice number not found" in warnings
    assert "Date not found" in warnings
    assert "Total not found" in warnings


def test_date_in_another_format_is_flagged(client):
    body = post_pdf(client, build_invoice_pdf(issue_date="01/02/2026")).json()
    assert body["issue_date"] is None
    assert any("YYYY-MM-DD" in warning for warning in body["warnings"])


def test_missing_item_table_is_flagged(client):
    body = post_pdf(client, build_invoice_pdf(items=None)).json()
    assert body["items"] == []
    assert "Item table not found" in body["warnings"]


def test_unreadable_table_rows_are_skipped_with_a_warning(client):
    pdf = build_invoice_pdf(
        items=[
            ("Widget", "2", "$10.00", "$20.00"),
            ("Bad quantity", "many", "$1.00", "$1.00"),
            ("Bad price", "1", "abc", "$1.00"),
            ("Not a number", "1", "NaN", "$1.00"),
        ]
    )
    body = post_pdf(client, pdf).json()
    assert len(body["items"]) == 1
    skipped = [w for w in body["warnings"] if w.startswith("Skipped unreadable table row")]
    assert len(skipped) == 3


def test_text_without_any_invoice_fields(client):
    body = post_pdf(client, build_text_pdf(["INVOICE"])).json()
    assert body["vendor"] is None
    assert body["valid"] is False


# ---------- files that are not usable invoices ----------


def test_not_a_pdf_is_reported_not_an_http_error(client):
    response = post_pdf(client, b"this is not a pdf", "broken.pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["source"] == "broken.pdf"
    assert body["warnings"][0].startswith("Could not read PDF")


def test_empty_file(client):
    body = post_pdf(client, b"").json()
    assert body["valid"] is False
    assert body["warnings"][0].startswith("Could not read PDF")


def test_scanned_looking_pdf_is_explained(client):
    body = post_pdf(client, build_blank_pdf()).json()
    assert body["valid"] is False
    assert "scanned PDF" in body["warnings"][0]


def test_too_many_pages(client_factory):
    client = client_factory(max_pages=2)
    body = post_pdf(client, build_text_pdf(["page"], pages=3)).json()
    assert body["valid"] is False
    assert body["warnings"] == ["PDF has 3 pages, the limit is 2"]


def test_pdf_with_no_pages(client, monkeypatch):
    class EmptyPdf:
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    from app import extractor

    monkeypatch.setattr(extractor.pdfplumber, "open", lambda stream: EmptyPdf())
    assert post_pdf(client, b"%PDF-1.4").json()["warnings"] == ["PDF has no pages"]


# ---------- upload limits and bad requests ----------


def test_file_over_the_size_limit_is_rejected(client_factory):
    client = client_factory(max_upload_mb=1)
    response = post_pdf(client, b"0" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]


def test_file_exactly_at_the_limit_is_accepted(client_factory):
    client = client_factory(max_upload_mb=1)
    response = post_pdf(client, b"0" * (1024 * 1024))
    assert response.status_code == 200


def test_missing_file_field(client):
    assert client.post("/extract").status_code == 422


# ---------- API key ----------


def test_no_key_configured_means_open_access(client):
    assert post_pdf(client, build_invoice_pdf()).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_missing_or_wrong_key_is_rejected(client_factory, headers):
    client = client_factory(api_key="secret")
    response = post_pdf(client, build_invoice_pdf(), headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "ApiKey"


def test_correct_key_is_accepted(client_factory):
    client = client_factory(api_key="secret")
    response = post_pdf(client, build_invoice_pdf(), headers={"X-API-Key": "secret"})
    assert response.status_code == 200


def test_health_stays_public_when_a_key_is_set(client_factory):
    assert client_factory(api_key="secret").get("/health").status_code == 200


# ---------- tables and rows that must not confuse the parser ----------


def test_other_tables_in_the_pdf_are_ignored(client):
    body = post_pdf(client, build_invoice_pdf(extra_table=True)).json()
    assert body["valid"] is True
    assert [item["description"] for item in body["items"]] == ["Widget"]


def test_empty_table_rows_are_ignored(client):
    pdf = build_invoice_pdf(items=[("Widget", "2", "$10.00", "$20.00"), ("", "", "", "")])
    body = post_pdf(client, pdf).json()
    assert body["valid"] is True
    assert len(body["items"]) == 1
