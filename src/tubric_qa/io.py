"""Small, explicit file contracts shared by CLI and reports."""

import csv
import hashlib
import json
import math
from pathlib import Path


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_tsv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Missing or duplicate TSV column names: {path}")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"TSV row width does not match header: {path}")
        return rows


def write_tsv(path, rows, fields):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, delimiter="\t", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: ("n/a" if row.get(key) is None else row.get(key, "n/a")) for key in fields}
            )


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def disjoint_output(output, inputs):
    output = Path(output).resolve()
    for item in inputs:
        if item is None:
            continue
        source = Path(item).resolve()
        if output == source or output in source.parents or source in output.parents:
            raise ValueError(f"Output must be separate from input: {source}")
    if output.exists():
        raise ValueError(f"Output already exists; choose a new directory: {output}")
    return output


def fingerprint(path, full=True):
    path = Path(path).resolve()
    stat = path.stat()
    result = {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if full:
        result["sha256"] = sha256(path)
    return result
