"""PyBIDS inventory and conservative MRIQC association."""

from collections import defaultdict
from pathlib import Path

import nibabel as nib
import numpy as np

from bids import BIDSLayout
from bids.layout import BIDSLayoutIndexer, parse_file_entities

from .config import METRICS
from .io import finite, read_json

IDENTITY = (
    "subject",
    "session",
    "task",
    "acquisition",
    "ceagent",
    "reconstruction",
    "direction",
    "run",
    "echo",
    "part",
    "chunk",
    "suffix",
)
ALLOWED_META = {
    "Manufacturer": "manufacturer",
    "ManufacturersModelName": "model",
    "SoftwareVersions": "software_version",
}
REPORT_SUFFIXES = ["bold", "T1w", "T2w"]
IMAGE_EXTENSIONS = [".nii", ".nii.gz"]


def entities(path):
    parsed = parse_file_entities(str(path), config=["bids", "derivatives"])
    return {key: str(parsed.get(key, "")) for key in IDENTITY}


def identity(path):
    return tuple(entities(path)[key] for key in IDENTITY)


def text(value):
    if isinstance(value, list):
        return "; ".join(map(str, value))
    return str(value) if value is not None else "unknown"


def normalize_selection(tasks=None, sessions=None):
    selection = {}
    for key, values, prefix in (("task", tasks, "task-"), ("session", sessions, "ses-")):
        labels = sorted({v.removeprefix(prefix) for v in (values or [])})
        if any(not v or not v.isascii() or not v.isalnum() for v in labels):
            raise ValueError(f"Invalid {key} label; use BIDS labels, not paths or wildcards")
        selection[key] = labels
    return selection


def selected(row, selection):
    return all(not labels or row[key] in labels for key, labels in (selection or {}).items())


def raw_layout(bids_dir, *, index_metadata):
    bids_dir = Path(bids_dir).resolve()
    description = read_json(bids_dir / "dataset_description.json")
    if description.get("DatasetType", "raw") != "raw":
        raise ValueError("--bids must be a raw BIDS dataset, not a derivative")
    # Keep all filename records, but do not build unused fieldmap/events/etc.
    # metadata associations. Never filter this index by task/session: generic
    # ancestor JSONs must remain available for PyBIDS metadata inheritance.
    indexer = BIDSLayoutIndexer(
        validate=False, index_metadata=index_metadata,
        suffix=REPORT_SUFFIXES, extension=list(IMAGE_EXTENSIONS),
    )
    return BIDSLayout(bids_dir, validate=False, derivatives=False, indexer=indexer)


def raw_image_paths(layout, selection):
    root = Path(layout.root)
    return [
        path for path in sorted(layout.get(
            suffix=REPORT_SUFFIXES, extension=IMAGE_EXTENSIONS, return_type="filename"
        ))
        if Path(path).relative_to(root).parts[0].startswith("sub-")
        and selected(entities(path), selection)
    ]


def metadata_paths(layout):
    # Retain the original conservative, dataset-wide JSON fingerprint contract.
    root = Path(layout.root)
    return {root / "dataset_description.json"} | {
        Path(p) for p in layout.get(extension=".json", return_type="filename")
        if "derivatives" not in Path(p).relative_to(root).parts
    }


def input_paths(bids_dir, selection=None):
    """Detect additions without rereading headers or rebuilding metadata tags."""
    layout = raw_layout(bids_dir, index_metadata=False)
    return {Path(p) for p in raw_image_paths(layout, selection)} | metadata_paths(layout)


def discover(bids_dir, selection=None, progress=None):
    progress = progress or (lambda message: None)
    bids_dir = Path(bids_dir).resolve()
    # Nonconforming-but-parseable target files remain visible rather than silently dropped.
    progress("Indexing BIDS paths and BOLD/T1w/T2w metadata (images are not processed)")
    layout = raw_layout(bids_dir, index_metadata=True)
    rows = []
    files = raw_image_paths(layout, selection)
    progress(f"Reading selected image headers and inherited metadata: {len(files)} candidates")
    for number, file in enumerate(files, 1):
        path = Path(file)
        relative = path.relative_to(bids_dir)
        row = entities(path)
        row.update(
            image_id=relative.as_posix(),
            bids_path=str(path),
            metadata_status="available",
            validation_issues=[],
            mriqc_status="missing",
            mriqc_path="",
            mriqc_version="unknown",
        )
        if not row["subject"] or (row["suffix"] == "bold" and not row["task"]):
            row["validation_issues"].append("missing_required_BIDS_entity")
        try:
            image = nib.load(path)
            row["image_shape"] = "x".join(map(str, image.shape))
            if row["suffix"] == "bold" and (len(image.shape) != 4 or image.shape[3] < 2):
                row["validation_issues"].append("invalid_BOLD_dimensions")
            if not np.isfinite(image.affine).all() or any(z <= 0 for z in image.header.get_zooms()):
                row["validation_issues"].append("invalid_image_geometry")
        except (OSError, ValueError, nib.filebasedimages.ImageFileError):
            row["validation_issues"].append("unreadable_image_header")
        try:
            metadata = layout.get_metadata(file)
            for key, target in ALLOWED_META.items():
                row[target] = text(metadata.get(key))
        except (ValueError, KeyError, TypeError) as exc:
            row["metadata_status"] = "invalid"
            row["validation_issues"].append(f"metadata_error:{type(exc).__name__}")
        for target in ALLOWED_META.values():
            row.setdefault(target, "unknown")
        row["applicable"] = row["part"] in ("", "mag")
        if not row["applicable"]:
            row["mriqc_status"] = "not_applicable"
        rows.append(row)
        if number % 50 == 0 or number == len(files):
            progress(f"Image headers and metadata: {number}/{len(files)}")
    if not rows:
        raise ValueError("No BOLD/T1w/T2w NIfTI inputs match the selection in raw sub-* directories")
    # Hash metadata, never serialize its contents (it may contain sensitive fields).
    metadata_inputs = metadata_paths(layout)
    counts = defaultdict(int)
    for row in rows:
        counts[tuple(row[key] for key in IDENTITY)] += 1
    for row in rows:
        if counts[tuple(row[key] for key in IDENTITY)] != 1:
            row["validation_issues"].append("duplicate_raw_identity")
    return rows, metadata_inputs


def mriqc_index(root, selection=None):
    result = defaultdict(list)
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"MRIQC root does not exist: {root}")
    for path in sorted(root.rglob("sub-*.json")):
        if path.name.endswith(("_bold.json", "_T1w.json", "_T2w.json")):
            if not selected(entities(path), selection):
                continue
            parsed = parse_file_entities(str(path), config=["bids", "derivatives"])
            if any(parsed.get(key) for key in ("space", "desc", "resolution", "density")):
                continue
            result[identity(path)].append(path)
    return result


def flatten(data):
    result = {}
    for key, value in data.items():
        if key in ("bids_meta", "provenance"):
            continue
        if isinstance(value, dict):
            result.update({f"{key}_{sub}": item for sub, item in value.items()})
        else:
            result[key] = value
    return result


def attach_mriqc(rows, roots, config, indexes=None):
    if indexes is None:
        indexes = [mriqc_index(root) for root in roots]
    used = set()
    for row in rows:
        row["software_label"] = config["software_labels"].get(
            row["software_version"], row["software_version"]
        )
        row["scanner_group"] = " | ".join(
            row[key] for key in ("manufacturer", "model", "software_label")
        )
        collected = {**METRICS, **config["metrics"]}
        row.update({metric: None for metric in collected})
        key = tuple(row[field] for field in IDENTITY)
        matches = [index.get(key, []) for index in indexes]
        candidates = next((group for group in matches if group), [])
        row["shadowed_mriqc_candidates"] = sum(map(len, matches)) - len(candidates)
        used.update(path for group in matches for path in group)
        if not row["applicable"]:
            continue
        if not candidates:
            continue
        if len(candidates) != 1:
            row["mriqc_status"] = "ambiguous"
            continue
        path = candidates[0]
        row["mriqc_path"] = str(path)
        try:
            data = read_json(path)
            metrics = flatten(data)
            expected = ("tsnr", "fd_mean") if row["suffix"] == "bold" else ("efc", "cjv")
            if not any(finite(metrics.get(key)) is not None for key in expected):
                raise ValueError("not_an_IQM_json")
            row["mriqc_version"] = text(data.get("provenance", {}).get("version"))
            for metric in collected:
                if row["suffix"] in collected[metric]["modalities"]:
                    number = finite(metrics.get(metric))
                    row[metric] = number if number is not None and number >= 0 else None
            widths = []
            for axis in "xyz":
                width, spacing = (
                    finite(metrics.get(f"fwhm_{axis}")),
                    finite(metrics.get(f"spacing_{axis}")),
                )
                row[f"fwhm_{axis}_vox"] = width
                row[f"spacing_{axis}_mm"] = spacing
                mm = (
                    width * spacing
                    if width is not None and spacing is not None and width > 0 and spacing > 0
                    else None
                )
                row[f"fwhm_{axis}_mm"] = mm
                widths.append(mm)
            if "fwhm_mean_mm" in config["metrics"]:
                row["fwhm_mean_mm"] = (
                    sum(widths) / 3 if all(v is not None for v in widths) else None
                )
            row["mriqc_status"] = "available"
        except (OSError, ValueError, TypeError, AttributeError):
            row["mriqc_status"] = "invalid"
    orphans = [
        {"mriqc_path": str(path), "reason": "no_exact_raw_image_match"}
        for index in indexes
        for paths in index.values()
        for path in paths
        if path not in used
    ]
    return used, orphans


def attach_extras(rows, path, config):
    from .io import read_tsv

    lookup = {row["image_id"]: row for row in rows}
    seen = set()
    for extra in read_tsv(path):
        key = extra.get("image_id")
        if key not in lookup or key in seen:
            raise ValueError(f"Unknown or duplicate extras image_id: {key}")
        seen.add(key)
        if not extra.get("metric_source"):
            raise ValueError("Extras require a metric_source column documenting their origin")
        for metric, value in extra.items():
            if metric in ("image_id", "metric_source"):
                continue
            if metric in METRICS or metric not in config["metrics"]:
                raise ValueError(
                    f"Extras cannot replace MRIQC metrics or add unconfigured metric: {metric}"
                )
            number = finite(value)
            if value not in ("", "n/a") and number is None:
                raise ValueError(f"Non-numeric extras metric: {key}: {metric}")
            lookup[key][metric] = number
        lookup[key]["extra_metric_source"] = extra["metric_source"]
