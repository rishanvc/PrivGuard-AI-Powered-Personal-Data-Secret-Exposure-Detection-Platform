"""Generate samples/secrets-finance-demo/: synthetic secrets and financial data (Cycle 6).

    backend/.venv/Scripts/python.exe samples/make_secrets_finance_demo.py

NOT committed (.gitignore, D-038). Every value is fake and grants access to
nothing, but the files hold strings in real credential and card formats, which
secret scanners and GitHub's push protection would report. So only this script
is committed; the files are generated on your own machine.

Uses the same runtime builders as the tests (backend/tests/engine/secret_fixtures.py).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from tests.engine import builders as b  # noqa: E402
from tests.engine import secret_fixtures as s  # noqa: E402

OUT = ROOT / "secrets-finance-demo"


def build() -> dict[str, str | bytes]:
    first_card, second_card = s.card_number("4"), s.card_number("53")
    return {
        "deploy.env": "\n".join([
            "# Synthetic values: none of these grant access to anything.",
            f"DATABASE_URL=postgres://app:{s.rand(16)}@db.internal.example:5432/app",
            f"GITHUB_TOKEN={s.github_token()}",
            f"AWS_ACCESS_KEY_ID={s.aws_key_id()}",
            f"AWS_SECRET_ACCESS_KEY={s.aws_secret_key()}",
            f"STRIPE_SECRET_KEY={s.stripe_test_key()}",
            "SMTP_PASSWORD=changeme",            # a placeholder: not reported
            "TOKEN_EXPIRY_SECONDS=3600",         # describes a secret rather than holding one
        ]) + "\n",
        "build-server.pem": "\n".join([s.pem_begin(), s.pem_body(), s.pem_body(), s.pem_end()]) + "\n",
        "settings.json": json.dumps({
            "apiSecret": s.rand(24),
            "session": s.jwt({"sub": "synthetic-user-42", "email": "synthetic"}),
            "x_request_signer": s.mixed(40),
            "integrity": f"sha512-{s.rand(86, s.B64)}==",  # random by design: not reported
            "logLevel": "info",
        }, indent=2) + "\n",
        "payments.csv": "\r\n".join([
            "Customer Name,Card Number,CVV,UPI ID,Account Number,IFSC",
            f"Asha Example,{s.grouped(first_card)},123,asha.example@okaxis,{s.rand(14, '0123456789')},HDFC0001234",
            f"Ravi Example,{s.grouped(second_card)},456,ravi.example@ybl,{s.rand(12, '0123456789')},SBIN0004321",
        ]) + "\r\n",
        "bank-letter.docx": b.docx_bytes(
            b.para(b.run("Dear Ms. Asha Example,"))
            + b.para(b.run(f"Beneficiary account: {s.rand(15, '0123456789')}"))
            + b.para(b.run("IFSC: ICIC0006789"))
            + b.para(b.run(f"IBAN: {s.grouped(s.iban('DE', 22))}"))
            + b.para(b.run("SWIFT: HDFCINBB"))
            + b.para(b.run(f"GSTIN: {s.gstin('29')}"))
            + b.para(b.run("Paid on 24/10/2026, UTR 430112345678"))
            + b.para(b.run("Sandbox test card: 4242 4242 4242 4242")),
            creator="Synthetic Author",
        ),
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, content in build().items():
        data = content.encode("utf-8") if isinstance(content, str) else content
        (OUT / name).write_bytes(data)
        print(f"wrote {OUT.name}/{name} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
