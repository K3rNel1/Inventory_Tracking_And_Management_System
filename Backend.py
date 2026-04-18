# Project: Inventory Tracking and Management System
# Author: Ali Zubair Shah
# GitHub: https://github.com/K3rNel1

import sqlite3
import os
import hashlib
import webbrowser
from datetime import datetime
from urllib.parse import quote

DB_NAME = "Inventory.db"

# Hide the database file on Windows
try:
    os.system(f'attrib +h {DB_NAME}')
except Exception:
    pass


# ─── Database Helper ──────────────────────────────────────────────────────────

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    # Book register table
    conn.execute(
        "CREATE TABLE IF NOT EXISTS register "
        "(bname TEXT NOT NULL, name TEXT PRIMARY KEY, mob INTEGER, "
        "doi TEXT NOT NULL, dor TEXT NOT NULL, rm TEXT)"
    )
    # Auth table — id is locked to 1, enforcing a single user
    conn.execute(
        "CREATE TABLE IF NOT EXISTS auth "
        "(id INTEGER PRIMARY KEY CHECK (id = 1), "
        "username TEXT NOT NULL, password_hash TEXT NOT NULL)"
    )
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _hash(password: str) -> str:
    """SHA-256 hash of a password string."""
    return hashlib.sha256(password.encode()).hexdigest()


def is_first_run() -> bool:
    """Return True if no user account exists yet."""
    conn = get_connection()
    row  = conn.execute("SELECT id FROM auth WHERE id = 1").fetchone()
    conn.close()
    return row is None


def create_user(username: str, password: str) -> bool:
    """Create the single user account. Fails silently if one already exists."""
    if not is_first_run():
        return False
    conn = get_connection()
    conn.execute(
        "INSERT INTO auth (id, username, password_hash) VALUES (1, ?, ?)",
        (username.strip(), _hash(password))
    )
    conn.commit()
    conn.close()
    return True


def verify_login(username: str, password: str) -> bool:
    """Return True if the username + password match stored credentials."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT username, password_hash FROM auth WHERE id = 1"
    ).fetchone()
    conn.close()
    if row is None:
        return False
    return row[0] == username.strip() and row[1] == _hash(password)


def change_password(username: str, old_password: str, new_password: str) -> bool:
    """Change password after verifying current credentials. Returns True on success."""
    if not verify_login(username, old_password):
        return False
    conn = get_connection()
    conn.execute(
        "UPDATE auth SET password_hash = ? WHERE id = 1",
        (_hash(new_password),)
    )
    conn.commit()
    conn.close()
    return True


def get_username() -> str:
    """Return the stored username, or empty string if none exists."""
    conn = get_connection()
    row  = conn.execute("SELECT username FROM auth WHERE id = 1").fetchone()
    conn.close()
    return row[0] if row else ""


# ═══════════════════════════════════════════════════════════════════════════════
#  CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def issue_book(bname, name, mob, doi, dor, rm):
    """Insert or replace a book issue record. Returns True on success."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO register (bname, name, mob, doi, dor, rm) "
        "VALUES (?,?,?,?,?,?)",
        (bname, name, int(mob), doi, dor, rm)
    )
    conn.commit()
    conn.close()
    return True


def get_all_records():
    """Return all records as a list of tuples (bname, name, mob, doi, dor, rm)."""
    conn = get_connection()
    rows = conn.execute("SELECT bname, name, mob, doi, dor, rm FROM register").fetchall()
    conn.close()
    return rows


def get_record(borrower_name):
    """Return a single record by borrower name, or None if not found."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT bname, name, mob, doi, dor, rm FROM register WHERE name=?",
        (borrower_name,)
    ).fetchone()
    conn.close()
    return row


def update_record(borrower_name, new_bname=None, new_mob=None,
                  new_doi=None, new_dor=None, new_rm=None):
    """Update one or more fields for a given borrower. Returns True on success."""
    conn = get_connection()
    if new_bname:
        conn.execute("UPDATE register SET bname=? WHERE name=?", (new_bname, borrower_name))
    if new_mob:
        conn.execute("UPDATE register SET mob=? WHERE name=?", (int(new_mob), borrower_name))
    if new_doi:
        conn.execute("UPDATE register SET doi=? WHERE name=?", (new_doi, borrower_name))
    if new_dor:
        conn.execute("UPDATE register SET dor=? WHERE name=?", (new_dor, borrower_name))
    if new_rm is not None:
        conn.execute("UPDATE register SET rm=? WHERE name=?", (new_rm, borrower_name))
    conn.commit()
    conn.close()
    return True


def delete_record(borrower_name):
    """Delete a record by borrower name. Returns True on success."""
    conn = get_connection()
    conn.execute("DELETE FROM register WHERE name=?", (borrower_name,))
    conn.commit()
    conn.close()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  OVERDUE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

_DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"]


def _parse_date(date_str):
    """Try several common date formats; return datetime or None."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    return None


def get_overdue_records():
    """
    Return a list of dicts for every record whose return date has passed.
    Dict keys: bname, name, mob, doi, dor, rm, days_overdue
      days_overdue == 0  → due today
      days_overdue  > 0  → overdue by that many days
    Sorted most-overdue first.
    """
    today  = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = []
    for bname, name, mob, doi, dor, rm in get_all_records():
        due = _parse_date(dor)
        if due is None:
            continue
        due   = due.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (today - due).days
        if delta >= 0:
            result.append(dict(
                bname=bname, name=name, mob=mob,
                doi=doi, dor=dor, rm=rm,
                days_overdue=delta
            ))
    result.sort(key=lambda r: r["days_overdue"], reverse=True)
    return result


def is_overdue(dor: str) -> bool:
    """Quick helper — True if the return date is today or in the past."""
    due = _parse_date(dor)
    if due is None:
        return False
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (today - due.replace(hour=0, minute=0, second=0, microsecond=0)).days >= 0


# ═══════════════════════════════════════════════════════════════════════════════
#  WHATSAPP MESSAGING
# ═══════════════════════════════════════════════════════════════════════════════

def generate_default_message(borrower_name: str, book_name: str,
                              dor: str, days_overdue: int) -> str:
    """Build a polite default reminder message."""
    if days_overdue == 0:
        urgency = "is due for return *today*"
    elif days_overdue == 1:
        urgency = "was due for return *yesterday*"
    else:
        urgency = f"was due for return *{days_overdue} days ago*"

    return (
        f"Dear {borrower_name},\n\n"
        f"This is a kind reminder that the book *\"{book_name}\"* {urgency} "
        f"(Return Date: {dor}).\n\n"
        f"Please return it at your earliest convenience.\n\n"
        f"Thank you \U0001f64f"
    )


def send_whatsapp_message(phone_number, message: str) -> tuple:
    """
    Open WhatsApp desktop with a pre-filled message to phone_number.
    phone_number must include country code (digits only, no + or spaces).
    Returns (success: bool, error_msg: str).
    """
    clean = "".join(filter(str.isdigit, str(phone_number)))
    if not clean:
        return False, "Phone number is empty or invalid."
    url = f"whatsapp://send?phone={clean}&text={quote(message)}"
    try:
        webbrowser.open(url)
        return True, ""
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def _cli_login():
    print("\n─── Library Register ───")
    if is_first_run():
        print("No account found. Create your account first.")
        username = input("Choose a username : ").strip()
        password = input("Choose a password : ")
        create_user(username, password)
        print("Account created! Please log in.\n")

    for attempt in range(3):
        username = input("Username : ")
        password = input("Password : ")
        if verify_login(username, password):
            print(f"\nWelcome, {username}!")
            return True
        remaining = 2 - attempt
        print(f"Invalid credentials.{' ' + str(remaining) + ' attempt(s) left.' if remaining else ''}")
    print("Too many failed attempts. Exiting.")
    return False


def main():
    st = int(input("\n1, Issue Book\n2, Access Register\n[1/2]: "))

    if st == 1:
        bname = input("Name of the Book : ")
        name  = input("Name of the Borrower : ")
        mob   = int(input(f"Contact number of {name} : "))
        doi   = input("Date of Issue : ")
        dor   = input("Date of Return : ")
        rm    = input("Remarks : ")
        issue_book(bname, name, mob, doi, dor, rm)
        print("\nTransaction Completed!")

    elif st == 2:
        data = get_all_records()
        if data:
            overdue_names = {r["name"] for r in get_overdue_records()}
            for bname, name, mob, doi, dor, rm in data:
                tag = "  *** OVERDUE ***" if name in overdue_names else ""
                print(
                    f"\n=>  Book's name     : {bname}{tag}\n"
                    f"    Borrower's name : {name}\n"
                    f"    Contact         : {mob}\n"
                    f"    Date of Issue   : {doi}\n"
                    f"    Date of Return  : {dor}\n"
                    f"    Remarks         : {rm}\n"
                )

            st2 = int(input(
                "\n1, Update Register\n2, Remove from Register\n3, Send WhatsApp Reminder\n[1/2/3]: "
            ))

            if st2 == 1:
                ch        = input("Enter Borrower Name: ")
                new_bname = input("New Book Name (leave blank to skip): ")
                new_mob   = input("New Mobile (leave blank to skip): ")
                new_doi   = input("New DOI (leave blank to skip): ")
                new_dor   = input("New DOR (leave blank to skip): ")
                new_rm    = input("New Remarks (leave blank to skip): ")
                update_record(ch,
                              new_bname=new_bname or None, new_mob=new_mob or None,
                              new_doi=new_doi or None, new_dor=new_dor or None,
                              new_rm=new_rm or None)
                print("\nRecord Updated!")

            elif st2 == 2:
                ch = input("Enter Borrower Name: ")
                delete_record(ch)
                print("\nRecord of", ch, "removed")

            elif st2 == 3:
                overdue = get_overdue_records()
                if not overdue:
                    print("\nNo overdue records found.")
                else:
                    print("\nOverdue borrowers:")
                    for i, r in enumerate(overdue, 1):
                        print(f"  {i}. {r['name']} — \"{r['bname']}\" — {r['days_overdue']} day(s) overdue")
                    ch  = input("Enter borrower name to send reminder: ")
                    rec = next((r for r in overdue if r["name"] == ch), None)
                    if rec:
                        default_msg = generate_default_message(
                            rec["name"], rec["bname"], rec["dor"], rec["days_overdue"]
                        )
                        print(f"\nDefault message:\n{'-'*40}\n{default_msg}\n{'-'*40}")
                        edit = input("Edit message (leave blank to use default): ").strip()
                        final_msg = edit if edit else default_msg
                        ok, err = send_whatsapp_message(rec["mob"], final_msg)
                        print("\nWhatsApp opened successfully!" if ok else f"\nFailed to open WhatsApp: {err}")
                    else:
                        print("\nBorrower not found in overdue list.")
            else:
                print("\nInvalid Option")
        else:
            print("\nNo records found.")


if __name__ == "__main__":
    if _cli_login():
        while True:
            main()
