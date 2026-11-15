"""Create invoices that should be sent to review, for testing the pipeline.

Run from the project root:  python scripts/make_problem_samples.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from tests.pdfs import build_invoice_pdf  # noqa: E402

SAMPLES = ROOT / "samples"


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    (SAMPLES / "problem_wrong_total.pdf").write_bytes(
        build_invoice_pdf(number="INV-9001", total="$99.00")
    )
    (SAMPLES / "problem_missing_date.pdf").write_bytes(
        build_invoice_pdf(number="INV-9002", issue_date=None)
    )
    (SAMPLES / "problem_not_a_pdf.pdf").write_text("this is not a pdf")
    print("Created 3 problem invoices in", SAMPLES)


if __name__ == "__main__":
    main()