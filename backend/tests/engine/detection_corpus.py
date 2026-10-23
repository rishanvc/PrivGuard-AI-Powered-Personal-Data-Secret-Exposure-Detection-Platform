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

Case = namedtuple("Case", "text location expected gap")


def case(text, *expected, gap=False, **location):
    return Case(text, location, tuple(expected), gap)


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
    case("Card 4111 1111 1111 1111"),
    case("Card 5555 5555 5555 4444"),
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
