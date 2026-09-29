"""Versioned customer-record contract; no guessing missing business facts."""
import re
from copy import deepcopy

from .models import Finding, Inspection

POLICY_VERSION = "customer-v1"
COUNTRIES = {"US", "CA", "GB", "DE", "FR", "IN", "AU"}
ALIASES = {"USA": "US", "UNITED STATES": "US", "UK": "GB", "UNITED KINGDOM": "GB"}
FIELDS = {"record_id", "email", "age", "country", "status", "notes"}
REQUIRED = FIELDS - {"notes"}


def inspect(record: dict, seen: set[str] | None = None) -> Inspection:
    out = Inspection(deepcopy(record), deepcopy(record))

    def finding(code, name, severity, reason):
        out.findings.append(Finding(code, name, severity, reason))

    def change(name, value):
        old = out.candidate[name]
        if type(old) is not type(value) or old != value:
            out.changes[name] = {"before": record[name], "after": value}
            out.candidate[name] = value

    for name in sorted(record):
        value = record[name]
        if name not in FIELDS:
            finding("UNKNOWN_FIELD", name, "hard", "Field is outside the customer-v1 contract.")
        elif isinstance(value, str):
            change(name, value.strip())
    for name in sorted(REQUIRED):
        if out.candidate.get(name) is None or out.candidate.get(name) == "":
            finding("MISSING_REQUIRED", name, "hard", "Required value is missing.")
    for name in sorted(FIELDS - {"age"}):
        value = out.candidate.get(name)
        if value is not None and not isinstance(value, str):
            finding("INVALID_TYPE", name, "hard", "Expected a string.")
        elif isinstance(value, str) and len(value) > (2000 if name == "notes" else 320):
            finding("TOO_LONG", name, "hard", "Field exceeds its size limit.")
    identifier = out.candidate.get("record_id")
    if isinstance(identifier, str) and identifier:
        if seen is not None:
            if identifier in seen:
                finding("DUPLICATE_ID", "record_id", "hard", "ID already appeared in this input.")
            seen.add(identifier)
    email = out.candidate.get("email")
    if isinstance(email, str) and email:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            finding("INVALID_EMAIL", "email", "hard", "Email fails the documented basic format check.")
        else:
            local, domain = email.rsplit("@", 1)
            change("email", local + "@" + domain.lower())
    age = out.candidate.get("age")
    if isinstance(age, str) and re.fullmatch(r"[0-9]{1,3}", age):
        change("age", int(age))
        age = out.candidate["age"]
    if type(age) is not int or not 0 <= age <= 120:
        finding("INVALID_AGE", "age", "hard", "Age must be an integer between 0 and 120.")
    elif age > 100:
        finding("UNUSUAL_AGE", "age", "soft", "Age exceeds the review threshold of 100.")
    country = out.candidate.get("country")
    if isinstance(country, str) and country:
        change("country", ALIASES.get(country.upper(), country.upper()))
        if out.candidate["country"] not in COUNTRIES:
            finding("INVALID_COUNTRY", "country", "hard", "Country is outside the supported market list.")
    status = out.candidate.get("status")
    if isinstance(status, str) and status:
        change("status", status.lower())
        if out.candidate["status"] not in {"active", "inactive", "pending"}:
            finding("INVALID_STATUS", "status", "hard", "Status must be active, inactive, or pending.")
    notes = out.candidate.get("notes")
    if isinstance(notes, str) and notes:
        # Non-empty free text is always reviewed, avoiding regex-only semantic screening.
        finding("FREE_TEXT_REVIEW", "notes", "soft", "Free text needs a consistency judgment.")
    return out
