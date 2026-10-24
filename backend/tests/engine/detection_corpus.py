"""A synthetic corpus for MEASURING detectors (SRS 12.4): positives, look-alike
negatives, and known gaps.

Every value is synthetic. Aadhaar-format numbers are built with a valid
Verhoeff check digit so they exercise the real checksum; like any 12 digits,
one could coincide with an issued number, but on its own - with no name or any
other attribute - such a number identifies no one. Phone numbers use Ofcom's
fiction range (020 7946 0xxx) or the "98765 43210" placeholder common in
Indian documentation. Email domains are invented.

Known gaps are positives the Cycle 5 rules CANNOT find: names in free prose
with nothing labelling them (decision: context rules, no ML model). They stay
in the corpus so the recall figure shows that cost instead of hiding it.
"""

from collections import namedtuple

from privguard_engine.detectors import verhoeff_check_digit

Case = namedtuple("Case", "text location expected gap file_type")


def case(text, *expected, gap=False, file_type="", **location):
    return Case(text, location, tuple(expected), gap, file_type)


def aadhaar(first_eleven: str, separator: str = " ") -> str:
    digits = first_eleven + verhoeff_check_digit(first_eleven)
    return separator.join(digits[i:i + 4] for i in range(0, 12, 4))


def wrong_checksum(first_eleven: str) -> str:
    good = first_eleven + verhoeff_check_digit(first_eleven)
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    return " ".join(bad[i:i + 4] for i in range(0, 12, 4))


A1, A2 = aadhaar("23456789012"), aadhaar("34567890123")
A3, A4 = aadhaar("45678901234", ""), aadhaar("56789012345", "")
MAIL = "mailhost-synthetic.net"

CASES = [
    # ------------------------------------------------------------- email
    case(f"Contact: priya.sharma@{MAIL}", ("email_address", f"priya.sharma@{MAIL}")),
    case(f"rahul.verma@{MAIL}", ("email_address", f"rahul.verma@{MAIL}"), header="Email"),
    case(f'    "email": "kavya.reddy@{MAIL}",', ("email_address", f"kavya.reddy@{MAIL}")),
    case("Write to ana@example.com for the demo", ("email_address", "ana@example.com")),
    case(f"Escalations go to support@{MAIL}", ("email_address", f"support@{MAIL}")),
    case(f"ana.example@{MAIL}", ("email_address", f"ana.example@{MAIL}"), header="Email Address"),
    case("Use logo@2x.png for retina screens"),
    case("git clone git@github.com:synthetic-org/repo.git"),
    case("Server user@localhost refused the connection"),
    case("Apples @ 20.50 each"),
    case("Follow @synthetic_user for updates"),
    # ------------------------------------------------------------- phone
    case("Call +44 20 7946 0001 tomorrow", ("phone_number", "+44 20 7946 0001")),
    case("Mobile: 98765 43210", ("phone_number", "98765 43210")),
    case("WhatsApp +91 98765 43210 after six", ("phone_number", "+91 98765 43210")),
    case("9876543210", ("phone_number", "9876543210"), header="Phone"),
    case("Ph: 9876543210", ("phone_number", "9876543210")),
    case("Invoice 9876543210 paid in full"),
    case("Order shipped 2026-10-23 15:30"),
    case("Server 192.168.1.10 restarted"),
    case("Mobile: +44 7700 900123"),           # Ofcom's reserved drama range: not a real number
    case("Total: 12345678"),
    # ------------------------------------------------------------- Aadhaar
    case(f"Aadhaar: {A1}", ("aadhaar_number", A1)),
    case(f"Identity verified with {A2} on file", ("aadhaar_number", A2)),
    case(A3, ("aadhaar_number", A3), header="Aadhaar No"),
    case(f"Order reference {A4}"),              # valid checksum, but bare and unlabelled
    case(f"Aadhaar: {wrong_checksum('23456789012')}"),
    case("Aadhaar: 1234 5678 9012"),            # Aadhaar numbers never start with 0 or 1
    # Not Aadhaar. Since Cycle 6 they ARE found - as published test cards, which they are.
    case("Card 4111 1111 1111 1111", ("test_payment_card", "4111 1111 1111 1111")),
    case("Card 5555 5555 5555 4444", ("test_payment_card", "5555 5555 5555 4444")),
    # ------------------------------------------------------------- PAN
    case("PAN: ABCPE1234F", ("pan_number", "ABCPE1234F")),
    case("BNZPM2501F", ("pan_number", "BNZPM2501F"), header="PAN"),
    case("Vendor PAN AAACX1234Z on the invoice", ("pan_number", "AAACX1234Z")),
    case("Product code ABCDE1234F"),            # 4th letter D is not a PAN holder type
    case("pan: abcpe1234f"),                    # PANs are written in capitals
    # ------------------------------------------------------------- dates of birth
    case("DOB: 17/05/1990", ("date_of_birth", "17/05/1990")),
    case("Date of birth - 3 March 1985", ("date_of_birth", "3 March 1985")),
    case("1992-11-08T00:00:00", ("date_of_birth", "1992-11-08T00:00:00"), header="Date of Birth"),
    case("She was born on March 3, 1985 in Pune", ("date_of_birth", "March 3, 1985")),
    case("Invoice date: 17/05/1990"),
    case("DOB: 31/02/1990"),                    # no such date
    case("DOB: 17/05/2090"),                    # in the future
    case("Meeting moved to 17/05/1990"),
    # ------------------------------------------------------------- people's names
    case("Ana Example", ("person_name", "Ana Example"), header="Name"),
    case("Priya Sharma", ("person_name", "Priya Sharma"), header="Employee Name"),
    case("Name: Rahul Verma", ("person_name", "Rahul Verma")),
    case('    "full_name": "Lakshmi Devi Iyer",', ("person_name", "Lakshmi Devi Iyer")),
    case("Dear Ms. Kavya Reddy,", ("person_name", "Kavya Reddy")),
    case("Approved by Smt. Lakshmi Devi", ("person_name", "Lakshmi Devi")),
    case("Synthetic Author", ("person_name", "Synthetic Author"), part="properties", field="creator"),
    case("Synthetic Reviewer", ("person_name", "Synthetic Reviewer"), part="comments", field="author"),
    case("report.pdf", header="File name"),
    case("File name: report_final.pdf"),
    case("Host name: build-server-01"),
    case("Dear Sir/Madam,"),
    case("N/A", header="Name"),
    case("Name:"),
    case("Please call Priya Sharma about the invoice.", ("person_name", "Priya Sharma"), gap=True),
    case("Ana Example will review the contract tomorrow.", ("person_name", "Ana Example"), gap=True),
    case("The report was prepared by Rahul Verma and Kavya Reddy.",
         ("person_name", "Rahul Verma"), ("person_name", "Kavya Reddy"), gap=True),
    # ------------------------------------------------------------- several in one line
    case("Name: Rahul Verma, Mobile: 98765 43210, DOB: 17/05/1990",
         ("person_name", "Rahul Verma"), ("phone_number", "98765 43210"), ("date_of_birth", "17/05/1990")),
    # ------------------------------------------------------------- personal-record fields
    case("EMP-1042", ("employee_id", "EMP-1042"), header="Employee ID"),
    case("Passport No: K1234567", ("passport_number", "K1234567")),
    case("Female", ("gender", "Female"), header="Gender"),
    case("Hindu", ("religion_or_caste", "Hindu"), header="Religion"),
    case("Blood group: B+", ("blood_group", "B+")),
    case("Passport photo: attached"),
    case("Passport-size photograph required"),
    case("-", header="Gender"),
    # ------------------------------------------------------------- addresses
    case("12 MG Road, Bengaluru 560001", ("postal_address", "12 MG Road, Bengaluru 560001"), header="Address"),
    case("Residential address: 45 Park Street, Kolkata 700016",
         ("postal_address", "45 Park Street, Kolkata 700016")),
    case("PIN code: 560001", ("postal_code", "560001")),
    case("192.168.1.10", header="IP address"),
    case("IP address: 10.0.0.1"),
    case("Order total 560001"),
]

# Written AFTER the first measurement, deliberately to break the rules above:
# messier formatting, other spellings, and look-alikes the first batch didn't cover.
HARDER_CASES = [
    case(f"Contact Priya at priya.sharma@{MAIL}.", ("email_address", f"priya.sharma@{MAIL}")),
    case(f"Email:neha.gupta@{MAIL}", ("email_address", f"neha.gupta@{MAIL}")),
    case(f"PRIYA.SHARMA@{MAIL.upper()}", ("email_address", f"PRIYA.SHARMA@{MAIL.upper()}")),
    case(f"<a href='mailto:arjun@{MAIL}'>mail</a>", ("email_address", f"arjun@{MAIL}")),
    case("Call +91-98765-43210 today", ("phone_number", "+91-98765-43210")),
    case("Tel: (022) 2345 6789", ("phone_number", "(022) 2345 6789")),
    case("Call me on 098765 43210", ("phone_number", "098765 43210")),
    case("ISBN 978-0-306-40615-7"),
    case("Tracking number 1Z999AA10123456784"),
    case("Location 12.9716, 77.5946"),
    case("Price Rs. 98,765.43 incl. tax"),
    case(f"Aadhaar No.: {aadhaar('23456789012', '-')}", ("aadhaar_number", aadhaar("23456789012", "-"))),
    case(f"UID {A4}", ("aadhaar_number", A4)),
    case("D.O.B.: 05-Jan-1991", ("date_of_birth", "05-Jan-1991")),
    case("Birthday: 1st April 1988", ("date_of_birth", "1st April 1988")),
    case("Born to run, released in 1975"),
    case("Contract dates: start 01/04/2026, end 31/03/2027"),
    case("Name : Arjun Mehta", ("person_name", "Arjun Mehta")),
    case("NAME: ARJUN MEHTA", ("person_name", "ARJUN MEHTA")),
    case("Customer Name - Neha Gupta", ("person_name", "Neha Gupta")),
    case("Name: Neha", ("person_name", "Neha")),
    case("Dear Dr Rao,", ("person_name", "Rao")),
    case("Name of the project: Apollo"),
    case("Rename: done"),
    case("Username: ana_ex"),
    case("User name: ana_ex"),
    case("Northwind Traders", header="Company Name"),
    case("Signed: Vikram Singh", ("person_name", "Vikram Singh"), gap=True),
    case("Gender: M", ("gender", "M")),
    case("Sex education workshop at 5pm"),
    case("Address - Flat 4B, Lake View Apartments, Pune 411001",
         ("postal_address", "Flat 4B, Lake View Apartments, Pune 411001")),
    case(f"Email address: ana@{MAIL}", ("email_address", f"ana@{MAIL}")),
    case("MAC address: 00:1B:44:11:3A:B7"),
    case("Pincode 411001", ("postal_code", "411001")),
    case("Invoice ABCPE1234F attached", ("pan_number", "ABCPE1234F")),
    # Found by probing, not by the batches above: fields run together on one line.
    case("Customer Name: Neha Gupta Order ID: 4421", ("person_name", "Neha Gupta")),
    case("Name: Ana Example Date: 17/05/2026", ("person_name", "Ana Example")),
    case("Customer Name: Neha Gupta Phone: 98765 43210",
         ("person_name", "Neha Gupta"), ("phone_number", "98765 43210")),
    case("Approved by Mr. Arjun Mehta Ref 4521", ("person_name", "Arjun Mehta")),
    case("Name Ana Example   Phone 98765 43210",                      # table layout, no colons
         ("person_name", "Ana Example"), ("phone_number", "98765 43210"), gap=True),
    # Blank forms and templates: labels with no values (found by a worst-case timing probe).
    case("First Name: Last Name: Email:"),
    case(f"Name: Email: ana@{MAIL}", ("email_address", f"ana@{MAIL}")),
    case("Name: Name"),
    case("Full name: ______  Date: ________"),
    # From samples/extraction-demo. A DOCX table's label sits in the NEIGHBOURING
    # cell ("Customer" | "Ana Example"), which reaches the detectors as its own segment.
    case("Ana Example", ("person_name", "Ana Example"), gap=True, part="body", paragraph=5),
    case("Call Ana Example on +44 20 7946 0001 before the meeting.",
         ("person_name", "Ana Example"), ("phone_number", "+44 20 7946 0001"), gap=True, slide=2, part="notes"),
]


# ------------------------------------------------------------------ secrets (Cycle 6)
# Built at runtime from tests/engine/secret_fixtures.py: no credential-shaped
# literal exists in this file. `file_type` is what intake would have decided.

def _secret_cases():
    from . import secret_fixtures as s

    pem = s.pem_begin()
    block = "\n".join([pem, s.pem_body(), s.pem_body(), s.pem_end()])
    gcp_key = s.join(s.pem_begin("PRIVATE KEY"), "\n", s.pem_body(), "\n", s.pem_end("PRIVATE KEY"))
    aws_id, aws_secret, aws_doc = s.aws_key_id(), s.aws_secret_key(), s.aws_documentation_key_id()
    github, gitlab, slack = s.github_token(), s.gitlab_token(), s.slack_bot_token()
    live, test, google, openai = s.stripe_live_key(), s.stripe_test_key(), s.google_api_key(), s.openai_key()
    hf, sendgrid, telegram, azure = s.huggingface_token(), s.sendgrid_key(), s.telegram_bot_token(), s.azure_account_key()
    token, personal_token, bearer = s.jwt(), s.jwt({"sub": "42", "email": "synthetic"}), s.rand(40, s.URLSAFE)
    basic = __import__("base64").b64encode(s.join("svc-backup:", s.password()).encode()).decode()
    pw1, pw2, pw3, pw4, pw5, pw6 = (s.rand(16) for _ in range(6))
    secret1, secret2, spoken = s.rand(24), s.rand(50), s.password()
    unlucky, random_value = s.mixed(32), s.mixed(40)

    return [
        # -- private keys
        case(pem, ("private_key", pem), file_type="key", line=1),
        case(block, ("private_key", block), part="body", paragraph=3),
        case(s.pem_begin("OPENSSH PRIVATE KEY"), ("private_key", s.pem_begin("OPENSSH PRIVATE KEY")), file_type="key"),
        case(f'  "private_key": "{gcp_key}\n",', ("private_key", gcp_key), file_type="json"),
        case(s.pem_begin("PUBLIC KEY"), file_type="key"),
        case(s.pem_begin("CERTIFICATE"), file_type="key"),
        # -- known formats
        case(f"aws_access_key_id = {aws_id}", ("cloud_credential", aws_id), file_type="config"),
        case(f"aws_secret_access_key = {aws_secret}", ("cloud_credential", aws_secret), file_type="config"),
        case(f"AWS_ACCESS_KEY_ID={aws_doc}", ("test_api_token", aws_doc), file_type="env"),
        case(f"GITHUB_TOKEN={github}", ("api_token", github), file_type="env"),
        case(f"  token: {gitlab}", ("api_token", gitlab), file_type="yaml"),
        case(f"Bot token for the alerts channel: {slack}", ("api_token", slack), file_type="text"),
        case(f'stripe.api_key = "{live}"', ("api_token", live), file_type="code"),
        case(f'STRIPE_SECRET_KEY="{test}"', ("test_api_token", test), file_type="env"),
        case(f'const mapsKey = "{google}";', ("api_token", google), file_type="code"),
        case(f"OPENAI_API_KEY={openai}", ("api_token", openai), file_type="env"),
        case(f'login(token="{hf}")', ("api_token", hf), file_type="code"),
        case(f"SendGrid key: {sendgrid}", ("api_token", sendgrid), file_type="text"),
        case(f"BOT_TOKEN={telegram}", ("api_token", telegram), file_type="env"),
        case(f"DefaultEndpointsProtocol=https;AccountName=synthstore;AccountKey={azure};EndpointSuffix=core.windows.net",
             ("cloud_credential", azure), file_type="config"),
        case(f"AKIA{s.rand(16, 'abcdefghij')}", file_type="text"),          # lower case: not an AWS key ID
        case(s.join("sk", "_li", "ve_", s.rand(10)), file_type="text"),     # too short
        # -- tokens and headers
        case(f"Authorization: Bearer {token}", ("jwt", token), file_type="text"),
        case(f"session={personal_token}", ("jwt", personal_token), file_type="text"),
        case(f"curl -H 'Authorization: Bearer {bearer}'", ("secret_assignment", bearer), file_type="text"),
        case(f"Authorization: Basic {basic}", ("password", basic), file_type="text"),
        case(f"eyJ{s.rand(20, s.URLSAFE)}.eyJ{s.rand(20, s.URLSAFE)}.{s.rand(20)}", file_type="text"),  # not JSON
        case("Basic information about the project", file_type="text"),
        case("Bearer of bad news", file_type="text"),
        # -- connection strings
        case(f"DATABASE_URL=postgres://app:{pw1}@db.internal.example:5432/app",
             ("connection_string", f"postgres://app:{pw1}@db.internal.example:5432"), file_type="env"),
        case(f'MONGO_URI = "mongodb+srv://admin:{pw2}@cluster0.synthetic.net/?retryWrites=true"',
             ("connection_string", f"mongodb+srv://admin:{pw2}@cluster0.synthetic.net"), file_type="code"),
        case(f"REDIS_URL=redis://:{pw3}@cache:6379/0", ("connection_string", f"redis://:{pw3}@cache:6379"), file_type="env"),
        case("postgres://user:password@localhost/db", file_type="text"),    # documentation placeholder
        # -- settings named like secrets
        case(f"DB_PASSWORD={pw4}", ("password", pw4), file_type="env"),
        case(f"  password: {pw5}", ("password", pw5), file_type="yaml"),
        case(f'  "apiSecret": "{secret1}",', ("secret_assignment", secret1), file_type="json"),
        case(f"secret_key = {secret2}", ("secret_assignment", secret2), file_type="config"),
        case(f'ADMIN_PASSWORD = "{pw6}"', ("password", pw6), file_type="code"),
        case(f"Wi-Fi password: {spoken}", ("password", spoken), file_type="docx", part="body", paragraph=2),
        case(f"<password>{pw1}</password>", ("password", pw1), file_type="xml"),
        case(pw2, ("password", pw2), file_type="csv", header="Password", row=2, column=3),
        case(f'  "x_request_signer": "{random_value}",', ("high_entropy_secret", random_value), file_type="json"),
        # Random, but its characters repeat (4.09 bits/char): it scores like an identifier.
        # Entropy alone misses ~2% of 32-character keys - measured, and kept visible (D-037).
        case(f'  "x_upstream_signer": "{unlucky}",', ("high_entropy_secret", unlucky), gap=True, file_type="json"),
        # -- look-alikes and placeholders: nothing to find
        case("DB_PASSWORD=changeme", file_type="env"),
        case("password: ${DB_PASSWORD}", file_type="yaml"),
        case('password = os.environ["DB_PASSWORD"]', file_type="code"),
        case('password = request.form["password"]', file_type="code"),
        case("password: str = Field(min_length=12)", file_type="code"),
        case("api_key: <your-api-key>", file_type="yaml"),
        case("TOKEN_EXPIRY_SECONDS=3600", file_type="env"),
        case("PASSWORD_MIN_LENGTH=12", file_type="env"),
        case("secret_name: db-credentials", file_type="yaml"),
        case("pass: true", file_type="yaml"),
        case("token: null", file_type="yaml"),
        case("max_tokens: 4096", file_type="yaml"),
        case("pwd: /home/synthetic", file_type="config"),
        case(f"csrf_token: {s.mixed(32)}", file_type="yaml"),
        case(f"client_id: {s.mixed(20)}", file_type="yaml"),
        case(f'  "integrity": "sha512-{s.rand(86, s.B64)}==",', file_type="json"),
        case(f"commit {s.rand(40, s.HEX)}", file_type="text"),
        case("id: 550e8400-e29b-41d4-a716-446655440000", file_type="yaml"),
        case("The password is changed every 90 days.", file_type="text"),
        case("Password: reset", file_type="text"),
        case("Wi-Fi password: see the vault", file_type="text"),
        case("AccountName=synthstore;AccountKey=<your-key>", file_type="config"),
    ]


SECRET_CASES = _secret_cases()


# ------------------------------------------------------------------ financial (Cycle 6)
# Synthetic numbers with real check digits, built at runtime. IFSC and SWIFT
# codes name bank BRANCHES - public directory data, not anyone's account.

def _financial_cases():
    from . import secret_fixtures as s

    visa, mastercard, column_card = s.card_number("4"), s.card_number("53"), s.card_number("4")
    amex, rupay = s.card_number("37", 15), s.card_number("6080")
    amex_shown = f"{amex[:4]} {amex[4:10]} {amex[10:]}"
    account, column_account, spaced = s.rand(14, "0123456789"), s.rand(11, "0123456789"), s.rand(12, "0123456789")
    spaced = f"{spaced[:4]} {spaced[4:8]} {spaced[8:]}"
    beneficiary = s.rand(15, "0123456789")
    gst = s.gstin("29")
    german, british = s.iban("DE", 22), s.iban("GB", 22)

    return [
        # -- payment cards
        case(f"Card no: {s.grouped(visa)}", ("payment_card", s.grouped(visa))),
        case(f"credit card {mastercard}", ("payment_card", mastercard)),
        case(column_card, ("payment_card", column_card), header="Card Number", file_type="csv", row=2, column=4),
        case(f"Amex {amex_shown}", ("payment_card", amex_shown)),
        case(f"RuPay debit card {s.grouped(rupay)}", ("payment_card", s.grouped(rupay))),
        case('STRIPE_TEST_CARD = "4242424242424242"', ("test_payment_card", "4242424242424242"), file_type="code"),
        case(f"Order {s.card_number('4')} shipped"),                         # passes Luhn, but bare and unlabelled
        case(f"Card no: {s.grouped(s.wrong_last_character(visa))}"),         # fails Luhn
        case("Ref 1234 5678 9012 3452"),                                     # no card network starts with 1
        case("Cards: 4111 1111 1111 1111, 4242 4242 4242 4242",
             ("test_payment_card", "4111 1111 1111 1111"), ("test_payment_card", "4242 4242 4242 4242")),
        # Separated by a single space, the groups run on into the next number, so no boundary
        # is visible - the same rule that stops a match INSIDE a longer number (found by timing probe).
        case("Cards: 4111 1111 1111 1111 4242 4242 4242 4242",
             ("test_payment_card", "4111 1111 1111 1111"), ("test_payment_card", "4242 4242 4242 4242"), gap=True),
        # -- card security codes
        case("CVV: 123", ("card_security_code", "123")),
        case("CVV: 12345"),
        # -- bank accounts
        case(f"Account No: {account}", ("bank_account", account)),
        case(column_account, ("bank_account", column_account), header="Account Number", file_type="csv", row=2, column=2),
        case(f"A/C No: {spaced}", ("bank_account", spaced)),
        case("Account No: 1234"),
        case("Account name: Synthetic Traders"),
        case("Your previous account was 00-11-22 12345678.",                 # a UK sort code and account:
             ("bank_account", "12345678"), gap=True),                        # outside Cycle 6's scope
        # -- IFSC
        case("IFSC: HDFC0001234", ("ifsc_code", "HDFC0001234")),
        case("Branch SBIN0004321 (Koramangala)", ("ifsc_code", "SBIN0004321")),
        case("Part ABCD0123456 in stock"),                                   # IFSC-shaped, unknown bank, no label
        # -- UPI
        case("Pay to asha.example@okaxis", ("upi_id", "asha.example@okaxis")),
        case("UPI ID: 9876543210@ybl", ("upi_id", "9876543210@ybl")),
        case("UPI: ravi.example@newpsp", ("upi_id", "ravi.example@newpsp")),
        # -- GSTIN
        case(f"GSTIN: {gst}", ("gstin", gst)),
        case(f"GSTIN: {s.wrong_last_character(gst)}"),
        # -- IBAN
        case(f"IBAN: {german}", ("iban", german)),
        case(f"Pay into {s.grouped(british)} BIC CODE ON FILE", ("iban", s.grouped(british))),
        case(f"IBAN: {s.wrong_last_character(german)}"),
        case("Batch ZZ12 3456 7890 1234 5678 90"),                           # no such country
        # -- SWIFT/BIC
        case("SWIFT: HDFCINBB", ("swift_code", "HDFCINBB")),
        case("BIC: DEUTDEFF500", ("swift_code", "DEUTDEFF500")),
        case("PASSWORD BUSINESS CONTINUITY"),                                # BIC-shaped words, no label
        # -- transactions and payment references (FR-043)
        case("UTR: 412345678901", ("transaction_id", "412345678901")),
        case("Txn ID: T2610241234567", ("transaction_id", "T2610241234567")),
        case("Payment ref: PAY-2026-00042", ("payment_reference", "PAY-2026-00042")),
        case("Transaction ID: pending"),
        # Found by probing after the first measurement: labels without a colon, and a bare "Account".
        case("Paid via UPI to ravi.example@okhdfcbank on 24/10/2026, UTR 430112345678",
             ("upi_id", "ravi.example@okhdfcbank"), ("transaction_id", "430112345678")),
        case("IFSC code: HDFC0001234, Account: 50100123456789",
             ("ifsc_code", "HDFC0001234"), ("bank_account", "50100123456789")),
        case("SWIFT TRANSFER COMPLETED"),                                    # never space-separated
        case("Account name: Synthetic Traders"),
        # -- several in one line
        case(f"Beneficiary account: {beneficiary}, IFSC: ICIC0006789, UPI: asha.example@okicici",
             ("bank_account", beneficiary), ("ifsc_code", "ICIC0006789"), ("upi_id", "asha.example@okicici")),
    ]


FINANCIAL_CASES = _financial_cases()
