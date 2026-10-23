"""Date resolution for explicitly known templates, never locale guessing."""
from datetime import date, datetime
from email.utils import parsedate_to_datetime

VERSION = 'bank-dates-v1'


def header_date(value):
    try:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return parsedate_to_datetime(value).date()
    except (ValueError, TypeError, OverflowError):
        return None


def resolve(raw, format, message_date=None):
    if format != '%d-%m-%y':
        return datetime.strptime(raw, format).date().isoformat()
    reference = header_date(message_date)
    # Validate day/month without datetime's implicit century pivot.
    day, month, year = map(int, raw.split('-'))
    date(2000 + year, month, day)
    if reference is None:
        return None
    candidates = []
    for century in (reference.year // 100 * 100 - 100,
                    reference.year // 100 * 100,
                    reference.year // 100 * 100 + 100):
        try:
            candidate = date(century + year, month, day)
        except ValueError:
            continue
        # Allow delayed alerts and a one-day timezone boundary, not arbitrary
        # historical dates. The email header is context, not proof of posting.
        if -1 <= (reference - candidate).days <= 31:
            candidates.append(candidate)
    return candidates[0].isoformat() if len(candidates) == 1 else None
