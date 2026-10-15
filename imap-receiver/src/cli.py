"""One-shot IMAP diagnostics and capture; no background workers yet."""

import argparse
from contextlib import contextmanager
import imaplib
import os
from pathlib import Path
import ssl
import sys

import psycopg
from psycopg.rows import dict_row
from .database import connect


class SetupError(Exception):
    """Safe, locally generated diagnostic message."""


def read_password(reference):
    path = os.environ.get(f"{reference}_FILE")
    if not path:
        raise SetupError("Missing credential file setting.")
    # Read bytes to preserve whitespace and line endings exactly.
    password = Path(path).read_bytes().decode("utf-8")
    if not password:
        raise SetupError("Credential file is empty.")
    return password


def quote_mailbox(folder):
    if any(c in folder for c in '\r\n\x00'):
        raise SetupError("Invalid mailbox name.")
    try:
        folder.encode("ascii")
    except UnicodeEncodeError:
        raise SetupError("Non-ASCII folder names require modified UTF-7 support, not implemented yet.") from None
    return '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'


def select_target(db, args):
    rows = db.execute("""
        SELECT a.imap_host, a.imap_port, a.username, a.credential_ref,
               m.id, m.folder_path, m.initialized_at
        FROM imap_receiver.accounts a
        JOIN imap_receiver.mailboxes m ON m.account_id = a.id
        WHERE a.credential_ref = %s AND m.folder_path = %s
    """, (args.credential_ref, args.folder)).fetchall()
    if len(rows) != 1:
        raise SetupError("Expected exactly one matching mailbox; check credential reference and folder.")
    return rows[0]


@contextmanager
def open_mailbox(target):
    password = read_password(target["credential_ref"])
    client = imaplib.IMAP4_SSL(
        target["imap_host"], target["imap_port"],
        ssl_context=ssl.create_default_context(), timeout=20,
    )
    try:
        client.login(target["username"], password)
        status, data = client.select(quote_mailbox(target["folder_path"]), readonly=True)
        if status != "OK":
            raise SetupError("Read-only mailbox selection failed.")
        yield client, int(data[0])
    finally:
        try:
            client.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


def response_number(client, name):
    _, values = client.response(name)
    if not values or values[0] is None:
        raise SetupError(f"Server omitted {name}; checkpoint was not changed.")
    try:
        value = int(values[0])
    except (ValueError, TypeError):
        raise SetupError(f"Invalid {name}; checkpoint was not changed.") from None
    if not 1 <= value <= 4294967295:
        raise SetupError(f"Out-of-range {name}; checkpoint was not changed.")
    return value


def initialize(db, target):
    # Same advisory-lock key convention as the earlier JavaScript design.
    with db.transaction():
        lock = db.execute("""
            SELECT pg_try_advisory_xact_lock(
                hashtextextended(%s::text, 0)
            ) AS acquired
        """, (str(target["id"]),)).fetchone()
        if not lock["acquired"]:
            raise SetupError("Mailbox is owned by another worker.")
        current = db.execute("""
            SELECT initialized_at FROM imap_receiver.mailboxes
            WHERE id = %s FOR UPDATE
        """, (target["id"],)).fetchone()
        if current is None:
            raise SetupError("Mailbox no longer exists.")
        if current["initialized_at"] is not None:
            return False
        with open_mailbox(target) as (client, _):
            validity = response_number(client, "UIDVALIDITY")
            last_uid = response_number(client, "UIDNEXT") - 1
            db.execute("""
                UPDATE imap_receiver.mailboxes
                SET uid_validity = %s, last_uid = %s,
                    initialized_at = now(), last_scan_at = now(),
                    last_error_code = NULL
                WHERE id = %s
            """, (validity, last_uid, target["id"]))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check-db", "check-imap", "init-mailbox", "capture-once", "observe"])
    parser.add_argument("--credential-ref", default="BANKING_IMAP_PASSWORD")
    parser.add_argument("--folder", default="INBOX")
    args = parser.parse_args(argv)
    try:
        if args.command == 'observe':
            from .observer import observe
            return observe()
        # libpq reads existing PG* environment variables from Compose.
        with connect() as db:
            if args.command == "check-db":
                rows = db.execute("""
                    SELECT a.name, a.enabled AS account_enabled,
                           m.folder_path, m.enabled AS mailbox_enabled,
                           m.initialized_at IS NOT NULL AS initialized
                    FROM imap_receiver.accounts a
                    JOIN imap_receiver.mailboxes m ON m.account_id = a.id
                    ORDER BY a.name, m.folder_path
                """).fetchall()
                print("Database connection successful.")
                for row in rows:
                    print(row)
            else:
                target = select_target(db, args)
                if args.command == "check-imap":
                    with open_mailbox(target) as (client, count):
                        _, capability = client.capability()
                        idle = b"IDLE" in b" ".join(capability).upper().split()
                        print("IMAP authentication successful.")
                        print("Read-only: True")
                        print(f"Existing messages: {count}")
                        print(f"IDLE supported: {idle}")
                elif args.command == "capture-once":
                    from .capture import capture_once
                    result = capture_once(db, target, open_mailbox=open_mailbox,
                                          response_number=response_number, error=SetupError)
                    print("Capture committed:", result)
                else:
                    created = initialize(db, target)
                    print("Checkpoint created. Existing mail will be skipped." if created
                          else "Checkpoint already exists. Nothing changed.")
        return 0
    except SetupError as error:
        print(f"Setup check failed: {error}", file=sys.stderr)
    except Exception as error:
        # External exception messages can contain server responses or credentials.
        print(f"Setup check failed: {type(error).__name__}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
