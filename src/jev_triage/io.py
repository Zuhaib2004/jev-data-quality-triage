"""Strict input parsing; malformed files fail without publishing a partial run."""
import csv
import json
from pathlib import Path


class InputError(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("Duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(value):
    raise InputError("Non-finite JSON number")


def load_json(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def records(path):
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        if path.suffix.lower() == ".csv":
            reader = csv.DictReader(file, strict=True)
            names = reader.fieldnames
            if not names or len(names) != len(set(names)) or any(not n for n in names):
                raise InputError("CSV requires unique, non-empty headers")
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise InputError(f"CSV field count mismatch near line {reader.line_num}")
                yield row
        elif path.suffix.lower() == ".json":
            data = load_json(file.read())
            if not isinstance(data, list):
                raise InputError("JSON input must be an array of objects")
            for row in data:
                if not isinstance(row, dict):
                    raise InputError("Every JSON record must be an object")
                yield row
        elif path.suffix.lower() == ".jsonl":
            for number, line in enumerate(file, 1):
                if line.strip():
                    row = load_json(line)
                    if not isinstance(row, dict):
                        raise InputError(f"JSONL line {number} must be an object")
                    yield row
        else:
            raise InputError("Use a .csv, .json, or .jsonl file")
