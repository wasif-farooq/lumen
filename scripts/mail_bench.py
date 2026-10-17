# ruff: noqa: E501  (the mail templates read best one per line)
"""How well does the chat model sort mail into folders and spot what needs doing? About 200 made-up
mails (seeded, varied senders, wording and lengths, some deliberately ambiguous), each with its right
folder and, when it needs one, the expected to-do and deadline. One model call per mail (a JSON
schema); deadlines go through Lumen's own parser (lumen.planner.times) with the mail's date as now.

    uv run python scripts/mail_bench.py [--model qwen3.5:2b] [--n 200] [--show-errors]

Reports folder accuracy, precision per folder, precision of what would move at each confidence
threshold (automatic moves need about 95%), and how well to-dos and their deadlines are found.
Template mails are easier than real ones: treat the numbers as an upper bound.
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import ollama

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lumen.planner.times import parse_when  # noqa: E402

FOLDERS = {
    "Bills": "bills and statements to pay (electricity, phone, internet, credit card, rent, taxes due)",
    "Receipts": "receipts and confirmations of something already paid or ordered",
    "Newsletters": "newsletters, digests, marketing and promotions",
    "Notifications": "automatic notices from apps and services (security alerts, shipping updates, account changes)",
    "Travel": "flights, hotels, trains, bookings and itineraries",
    "Work": "work mail from colleagues, clients and the office",
    "Personal": "mail from friends and family, personal appointments",
}
MAIL_DATE = datetime(2026, 10, 13, 9, 0)  # a Tuesday morning

NAMES = [
    "Sara Khan",
    "Omar Malik",
    "Ayesha Raza",
    "Bilal Ahmed",
    "Hina Iqbal",
    "Daniel Ortiz",
    "Mei Lin",
    "Priya Nair",
    "Tom Becker",
    "Lena Fischer",
]
COMPANIES = ["Northwind", "Contoso", "Fabrikam", "Globex", "Initech", "Umbrella Labs"]
SHOPS = ["Daraz", "Amazon", "Foodpanda", "IKEA", "Decathlon", "Apple Store"]
DAYS = ["Friday", "Thursday", "Monday", "next Wednesday", "the 20th", "tomorrow"]

# (folder, from, subject, body, expected to-do keyword or None, deadline words in the mail or None)
T = [
    # ---------- Bills ----------
    (
        "Bills",
        "billing@kelectric.pk",
        "Your electricity bill for October",
        "Dear customer, your electricity bill of Rs {amt} for October is ready. Please pay by {day} to avoid a late payment surcharge. Account no. 4471-22.",
        "pay",
        "{day}",
    ),
    (
        "Bills",
        "noreply@ptcl.net.pk",
        "PTCL bill due",
        "Your internet bill of Rs {amt} is due on {day}. Pay online through the app or at any branch.",
        "pay",
        "{day}",
    ),
    (
        "Bills",
        "statements@{company}bank.com",
        "Your credit card statement is ready",
        "Hello {first}, your statement for September shows a balance of ${amt}. Minimum payment due: {day}. View it in online banking.",
        "pay",
        "{day}",
    ),
    (
        "Bills",
        "accounts@greenwoodapartments.com",
        "Rent for November",
        "Hi {first}, a reminder that November rent of ${amt} is due on {day}. Bank transfer details are unchanged.",
        "rent",
        "{day}",
    ),
    (
        "Bills",
        "noreply@fbr.gov.pk",
        "Income tax return deadline",
        "The last date to file your income tax return is {day}. File online at iris.fbr.gov.pk.",
        "tax",
        "{day}",
    ),
    (
        "Bills",
        "billing@jazz.com.pk",
        "Postpaid bill Rs {amt}",
        "Your postpaid bill for the month is Rs {amt}. Due date {day}.",
        "pay",
        "{day}",
    ),
    # ---------- Receipts ----------
    (
        "Receipts",
        "orders@{shop}.com",
        "Order #{num} confirmed",
        "Thanks for your order, {first}! We have received your payment of ${amt}. Items: 1 x wireless mouse. Estimated delivery: 3-5 days.",
        None,
        None,
    ),
    (
        "Receipts",
        "receipts@careem.com",
        "Your ride receipt",
        "Thanks for riding with Careem. Trip on Monday: Rs {amt}, paid by card. Rate your captain in the app.",
        None,
        None,
    ),
    (
        "Receipts",
        "payments@{company}.com",
        "Payment received - invoice {num}",
        "We confirm receipt of ${amt} for invoice {num}. Thank you for your business.",
        None,
        None,
    ),
    (
        "Receipts",
        "noreply@{shop}.com",
        "Your receipt from {shop}",
        "Receipt {num}. Total charged: ${amt}. Payment method: Visa ending 4242. Keep this email for your records.",
        None,
        None,
    ),
    (
        "Receipts",
        "store@apple.com",
        "Your Apple receipt",
        "Apple ID {first}@mail.com. iCloud+ 200 GB, monthly, ${amt}. This charge will appear on your statement.",
        None,
        None,
    ),
    # ---------- Newsletters ----------
    (
        "Newsletters",
        "digest@medium.com",
        "Your weekly reading list",
        "Top stories for you this week: 5 habits of productive engineers, why Rust is eating the world, and more. Unsubscribe.",
        None,
        None,
    ),
    (
        "Newsletters",
        "news@{shop}.com",
        "Flash sale: 50% off this weekend only!",
        "Don't miss out, {first}! Up to 50% off on electronics until Sunday midnight. Shop now. Unsubscribe from promotional emails.",
        None,
        None,
    ),
    (
        "Newsletters",
        "hello@substack.com",
        "The Pragmatic Weekly #{num}",
        "This week: how teams ship faster, a deep dive into caching, and three tools worth trying. You're receiving this because you subscribed.",
        None,
        None,
    ),
    (
        "Newsletters",
        "marketing@{company}.com",
        "Introducing our new product line",
        "We're excited to announce our autumn collection. Explore what's new and get free shipping on your first order.",
        None,
        None,
    ),
    (
        "Newsletters",
        "events@techconf.io",
        "Early-bird tickets now available",
        "TechConf 2027 early-bird tickets are on sale. Prices go up soon. Unsubscribe.",
        None,
        None,
    ),
    # ---------- Notifications ----------
    (
        "Notifications",
        "no-reply@accounts.google.com",
        "Security alert: new sign-in",
        "A new sign-in to your Google Account on a Windows device. If this was you, you don't need to do anything.",
        None,
        None,
    ),
    (
        "Notifications",
        "noreply@github.com",
        "[{company}/api] Pull request #{num} merged",
        "Merged #{num} into main. You are receiving this because you were mentioned.",
        None,
        None,
    ),
    (
        "Notifications",
        "tracking@{shop}.com",
        "Your package has shipped",
        "Good news! Your order #{num} has shipped and is on its way. Track your package in the app.",
        None,
        None,
    ),
    (
        "Notifications",
        "no-reply@whatsapp.com",
        "Your WhatsApp backup completed",
        "Your chat backup to Google Drive completed successfully.",
        None,
        None,
    ),
    (
        "Notifications",
        "noreply@{company}.com",
        "Your password was changed",
        "The password for your account was changed. If you didn't make this change, contact support.",
        None,
        None,
    ),
    (
        "Notifications",
        "calendar-notification@google.com",
        "Updated invitation: Team sync",
        "This event has been changed. More details in Google Calendar.",
        None,
        None,
    ),
    # ---------- Travel ----------
    (
        "Travel",
        "bookings@emirates.com",
        "Booking confirmed: Lahore to Dubai",
        "Dear {first}, your flight EK623 on 2 November is confirmed. Booking reference {ref}. Online check-in opens 48 hours before departure.",
        None,
        None,
    ),
    (
        "Travel",
        "reservations@booking.com",
        "Your hotel reservation in Istanbul",
        "Your stay at Hotel Bosphorus, 5-8 November, is confirmed. Confirmation number {num}. Free cancellation until {day}.",
        None,
        None,
    ),
    (
        "Travel",
        "noreply@piac.com.pk",
        "Check in now for your flight",
        "Check-in is open for PK305 Islamabad to Karachi tomorrow. Please check in online by {day} to choose your seat.",
        "check in",
        "{day}",
    ),
    (
        "Travel",
        "tickets@pakrail.gov.pk",
        "E-ticket: Green Line Express",
        "Your e-ticket for Karachi Cantt to Lahore, coach 4, seat 22. Show this ticket on boarding.",
        None,
        None,
    ),
    (
        "Travel",
        "visa@vfsglobal.com",
        "Visa appointment confirmation",
        "Your visa appointment is booked for {day} at 10:30 at the Islamabad centre. Bring your passport and two photos.",
        "visa appointment",
        "{day}",
    ),
    # ---------- Work ----------
    (
        "Work",
        "{name_lower}@{company}.com",
        "Q3 report",
        "Hi {first},\n\nCould you please send me the Q3 sales report by {day}? The board meeting is next week.\n\nThanks,\n{name}",
        "report",
        "{day}",
    ),
    (
        "Work",
        "{name_lower}@{company}.com",
        "Review my PR when you can",
        "Hey, I opened a pull request for the billing fix. Can you review it before {day}? No rush otherwise.",
        "review",
        "{day}",
    ),
    (
        "Work",
        "hr@{company}.com",
        "Action required: update your emergency contact",
        "All employees must update their emergency contact details in the HR portal by {day}.",
        "emergency contact",
        "{day}",
    ),
    (
        "Work",
        "{name_lower}@{company}.com",
        "Meeting notes from today",
        "Hi all, attached are the notes from today's planning meeting. Main decisions: launch in December, hire one more designer. No action needed.",
        None,
        None,
    ),
    (
        "Work",
        "{name_lower}@{company}.com",
        "Quick question about the invoice",
        "Hi {first}, the client says invoice {num} is missing the PO number. Can you resend it with the PO number by {day}?",
        "invoice",
        "{day}",
    ),
    (
        "Work",
        "it@{company}.com",
        "Laptop replacement",
        "Your new laptop is ready for pickup at the IT desk. Please bring the old one with you.",
        "laptop",
        None,
    ),
    # ---------- Personal ----------
    (
        "Personal",
        "{name_lower}@gmail.com",
        "Dinner on Saturday?",
        "Hey! We're having a few friends over on Saturday at 8. Would love it if you could come. Let me know by {day}!",
        "reply",
        "{day}",
    ),
    (
        "Personal",
        "{name_lower}@gmail.com",
        "Photos from the wedding",
        "Here are the photos from Ali's wedding, hope you like them! Miss you all.",
        None,
        None,
    ),
    (
        "Personal",
        "appointments@shifaclinic.pk",
        "Appointment confirmed",
        "Your appointment with Dr. Farooq is confirmed for {day} at 4:30 pm. Please arrive 15 minutes early.",
        "appointment",
        "{day}",
    ),
    (
        "Personal",
        "{name_lower}@yahoo.com",
        "Mama's birthday",
        "Don't forget Mama's birthday is on {day}! I'm ordering the cake, can you get flowers?",
        "flowers",
        "{day}",
    ),
    (
        "Personal",
        "{name_lower}@gmail.com",
        "Can you call me?",
        "Hi, can you call me this evening? It's about the house papers.",
        "call",
        "this evening",
    ),
    (
        "Personal",
        "school@beaconhouse.edu.pk",
        "Parent-teacher meeting",
        "The parent-teacher meeting for grade 5 is on {day} at 9 am. Please confirm your attendance.",
        "parent-teacher",
        "{day}",
    ),
    # ---------- tricky ones ----------
    (
        "Personal",
        "{name_lower}@gmail.com",
        "Split the electricity bill?",
        "Hey, the electricity bill came, it's Rs {amt} this month. Can you send me your half? Thanks!",
        "send",
        None,
    ),
    (
        "Receipts",
        "billing@kelectric.pk",
        "Payment received - thank you",
        "We have received your payment of Rs {amt} for the October electricity bill. Thank you.",
        None,
        None,
    ),
    (
        "Work",
        "{name_lower}@{company}.com",
        "Flight for the Dubai conference",
        "Hi {first}, please book your flight to Dubai for the conference and send me the itinerary by {day} so finance can approve it.",
        "book",
        "{day}",
    ),
    (
        "Notifications",
        "no-reply@{company}bank.com",
        "Transaction alert",
        "A payment of Rs {amt} was made with your card ending 1234 at {shop}.",
        None,
        None,
    ),
]


def make_mails(n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    mails = []
    for i in range(n):
        folder, sender, subject, body, todo, due = T[i % len(T)] if i < len(T) else rng.choice(T)
        name = rng.choice(NAMES)
        fill = {
            "amt": f"{rng.randint(12, 980) * 10:,}",
            "day": rng.choice(DAYS),
            "first": name.split()[0],
            "name": name,
            "name_lower": name.split()[0].lower(),
            "company": rng.choice(COMPANIES).lower(),
            "shop": rng.choice(SHOPS).lower().replace(" ", ""),
            "num": str(rng.randint(1000, 99999)),
            "ref": "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6)),
        }
        mails.append(
            {
                "from": sender.format(**fill),
                "subject": subject.format(**fill),
                "body": body.format(**fill),
                "folder": folder,
                "todo": todo,
                "due": due.format(**fill) if due else None,
            }
        )
    return mails


SCHEMA = {
    "type": "object",
    "properties": {
        "folder": {"type": "string", "enum": list(FOLDERS)},
        "confidence": {"type": "number"},
        "todo": {"type": "string"},
        "due": {"type": "string"},
    },
    "required": ["folder", "confidence", "todo", "due"],
}

PROMPT = """Sort this email into one folder and say if the user must do something.

Folders:
{folders}

Email
From: {sender}
Subject: {subject}

{body}

Answer as JSON:
- folder: one of the folders above
- confidence: 0 to 1, how sure you are of the folder
- todo: a short task the user must do because of this email ("pay the electricity bill"), or "" if nothing to do
- due: the deadline copied from the email's own words ("by Friday", "the 20th"), or "" if none"""


def ask(client: ollama.Client, model: str, mail: dict) -> dict:
    folders = "\n".join(f"- {k}: {v}" for k, v in FOLDERS.items())
    prompt = PROMPT.format(folders=folders, sender=mail["from"], subject=mail["subject"], body=mail["body"][:2000])
    r = client.chat(model=model, messages=[{"role": "user", "content": prompt}], format=SCHEMA, think=False,
                    options={"temperature": 0, "num_ctx": 4096, "num_predict": 200}, keep_alive="30m")  # fmt: skip
    try:
        return json.loads(r.message.content or "{}")
    except ValueError:
        return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:2b")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()
    client = ollama.Client(host="http://127.0.0.1:11434")
    client.generate(model=args.model, prompt="", keep_alive="30m")
    mails = make_mails(args.n)
    rows = []
    t0 = time.time()
    for i, m in enumerate(mails):
        got = ask(client, args.model, m)
        rows.append((m, got))
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(mails)} mails, {(time.time() - t0) / (i + 1):.1f} s each", flush=True)

    # ---------- folders ----------
    right = sum(g.get("folder") == m["folder"] for m, g in rows)
    print(f"\n{args.model}: folder right {right}/{len(rows)} ({100 * right / len(rows):.0f}%)")
    print(
        "  per folder (precision = of the mails put there, how many belong there; recall = of those that belong, how many got there):"
    )
    for f in FOLDERS:
        put = [m for m, g in rows if g.get("folder") == f]
        belong = [m for m, _ in rows if m["folder"] == f]
        p = sum(m["folder"] == f for m in put) / len(put) if put else 0
        r = sum(g.get("folder") == f for m, g in rows if m["folder"] == f) / len(belong) if belong else 0
        print(f"    {f:14s} precision {100 * p:5.1f}%  recall {100 * r:5.1f}%  ({len(belong)} mails)")
    print("  if only mails at or above a confidence are moved automatically:")
    for t in (0.5, 0.7, 0.8, 0.9, 0.95):
        moved = [(m, g) for m, g in rows if float(g.get("confidence") or 0) >= t]
        ok = sum(g.get("folder") == m["folder"] for m, g in moved)
        print(
            f"    >= {t:.2f}: moves {len(moved):3d} ({100 * len(moved) / len(rows):3.0f}% of mail), right {100 * ok / max(1, len(moved)):5.1f}%"
        )

    # ---------- to-dos ----------
    need = [(m, g) for m, g in rows if m["todo"]]
    none = [(m, g) for m, g in rows if not m["todo"]]
    found = sum(bool((g.get("todo") or "").strip()) for _, g in need)
    false = sum(bool((g.get("todo") or "").strip()) for _, g in none)
    words = sum(m["todo"].lower() in (g.get("todo") or "").lower() for m, g in need)
    print(f"\n  to-dos: found {found}/{len(need)} that need one; invented {false}/{len(none)} for mails that need none; "
          f"the task named right {words}/{len(need)}")  # fmt: skip
    with_due = [(m, g) for m, g in need if m["due"]]
    due_ok = 0
    for m, g in with_due:
        want, got = parse_when(m["due"], MAIL_DATE), parse_when(g.get("due") or "", MAIL_DATE)
        due_ok += bool(want and got and want.at.date() == got.at.date())
    print(f"  deadlines: right day {due_ok}/{len(with_due)} (through Lumen's parser, from the mail's date)")
    print(f"  {(time.time() - t0) / len(rows):.1f} s per mail")

    if args.show_errors:
        print("\nwrong folders:")
        for m, g in rows:
            if g.get("folder") != m["folder"]:
                print(
                    f"  want {m['folder']:13s} got {g.get('folder')!s:13s} ({g.get('confidence')})  {m['subject'][:60]}"
                )
    out = Path(__file__).resolve().parents[1] / "data" / "mail_bench_last.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([{"mail": m, "got": g} for m, g in rows], indent=1))


if __name__ == "__main__":
    main()
