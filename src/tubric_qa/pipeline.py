"""Transactional report builds and reproducibility verification."""

from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import shutil
import tempfile

from . import __version__
from .config import load_config
from .inventory import (
    IDENTITY, attach_extras, attach_mriqc, discover, mriqc_index, normalize_selection,
)
from .io import disjoint_output, fingerprint, read_json, sha256, write_json, write_tsv
from .report import figures, html_report, methods
from .statistics import calculate


def build(bids_dir, mriqc_dirs, output, config_path=None, extras=None, hash_images=False,
          *, tasks=None, sessions=None, progress=None):
    progress = progress or (lambda message: None)
    selection = normalize_selection(tasks, sessions)
    progress("Starting report-only build; MRIQC will not be launched")
    inputs = [bids_dir, *mriqc_dirs, config_path, extras]
    output = disjoint_output(output, inputs)
    config = load_config(config_path)
    rows, metadata = discover(bids_dir, selection, progress)
    progress(f"Indexing existing MRIQC results in {len(mriqc_dirs)} root(s)")
    indexes = [mriqc_index(root, selection) for root in mriqc_dirs]
    progress(f"Matching MRIQC results to {len(rows)} selected images")
    used, orphans = attach_mriqc(rows, mriqc_dirs, config, indexes=indexes)
    if extras:
        attach_extras(rows, extras, config)
    progress("Calculating independent within-group QC flags and summaries")
    thresholds, flags, summary = calculate(rows, config)
    required = {"bold": ("tsnr", "fd_mean"), "T1w": ("efc", "cjv"), "T2w": ("efc", "cjv")}
    state = {
        "schema_version": 1,
        "selection": selection,
        "n_images": len(rows),
        "n_subjects": len({r["subject"] for r in rows}),
        "n_applicable": sum(r["applicable"] for r in rows),
        "n_not_applicable": sum(not r["applicable"] for r in rows),
        "n_mriqc_available": sum(r["mriqc_status"] == "available" for r in rows),
        "n_mriqc_unresolved": sum(
            r["applicable"] and r["mriqc_status"] != "available" for r in rows
        ),
        "n_identity_or_metadata_issues": sum(bool(r["validation_issues"]) for r in rows),
        "n_missing_core_metrics": sum(
            r["applicable"] and any(r.get(m) is None for m in required[r["suffix"]]) for r in rows
        ),
        "n_images_flagged": sum(r["review_flag_count"] > 0 for r in rows),
        "n_orphan_mriqc": len(orphans),
        "exclusion_decisions_made": False,
        "mriqc_status_counts": dict(Counter(r["mriqc_status"] for r in rows)),
    }
    state["core_inputs_complete"] = not any(
        state[key]
        for key in ("n_mriqc_unresolved", "n_identity_or_metadata_issues", "n_missing_core_metrics")
    )
    # Capture all indexed candidates, including orphans, for reproducibility.
    all_iqms = {p for index in indexes for paths in index.values() for p in paths}
    paths = metadata | used | all_iqms | {Path(p).resolve() for p in (config_path, extras) if p}
    progress("Fingerprinting metadata and inputs" + (" (full image hashes requested)" if hash_images else " (image size/mtime only)"))
    receipts = [fingerprint(p) for p in sorted(paths)]
    receipts += [fingerprint(r["bids_path"], full=hash_images) for r in rows]
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".tubric-qa-", dir=output.parent))
    mask = os.umask(0)
    os.umask(mask)
    stage.chmod(0o777 & ~mask)
    try:
        progress("Writing report tables")
        write_json(stage / "config.json", config)
        write_json(stage / "validation.json", state)
        columns = [
            "image_id",
            *IDENTITY,
            "manufacturer",
            "model",
            "software_version",
            "software_label",
            "scanner_group",
            "applicable",
            "metadata_status",
            "mriqc_status",
            "mriqc_version",
            *config["metrics"],
            *[f"fwhm_{a}_mm" for a in "xyz"],
            *[f"fwhm_{a}_vox" for a in "xyz"],
            *[f"spacing_{a}_mm" for a in "xyz"],
            "threshold_group",
            "review_flag_count",
            "validation_issues",
            "mriqc_path",
            "shadowed_mriqc_candidates",
            "extra_metric_source",
        ]
        table = [{**r, "validation_issues": ";".join(r["validation_issues"])} for r in rows]
        write_tsv(stage / "run_qc.tsv", table, list(dict.fromkeys(columns)))
        write_tsv(
            stage / "flags.tsv",
            flags,
            ["image_id", "threshold_group", "metric", "value", "flag", "status"],
        )
        write_tsv(
            stage / "thresholds.tsv",
            thresholds,
            list(thresholds[0]) if thresholds else ["metric", "status"],
        )
        write_tsv(
            stage / "scanner_summary.tsv",
            summary,
            list(summary[0]) if summary else ["metric", "status"],
        )
        write_tsv(stage / "orphan_mriqc.tsv", orphans, ["mriqc_path", "reason"])
        progress("Rendering figures")
        links = figures(stage, rows, config, thresholds, progress=progress)
        html_report(stage, rows, config, links, state)
        methods(stage, config)
        versions = {
            name: importlib.metadata.version(name)
            for name in ("pybids", "numpy", "matplotlib", "nibabel")
        }
        provenance = {
            "package": "tubric-qa",
            "version": __version__,
            "selection": selection,
            "dependencies": versions,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "bids_root": str(Path(bids_dir).resolve()),
            "mriqc_roots_in_priority_order": [str(Path(p).resolve()) for p in mriqc_dirs],
            "image_fingerprint_mode": "sha256" if hash_images else "size_and_mtime_only",
            "inputs": receipts,
            "exclusion_decisions_made": False,
            "code_sha256": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")},
            "outputs": {
                p.relative_to(stage).as_posix(): sha256(p)
                for p in sorted(stage.rglob("*"))
                if p.is_file()
            },
        }
        write_json(stage / "provenance.json", provenance)
        # Refuse to publish a report from inputs modified during the build.
        progress("Verifying input fingerprints before publishing the report")
        verify_inputs(receipts)
        if output.exists():
            raise ValueError("Output appeared while building; refusing to replace it")
        stage.rename(output)
        progress(f"Report complete: {len(rows)} images, {len(links)} figures")
    except BaseException:
        shutil.rmtree(stage)
        raise
    return state


def verify_inputs(receipts):
    for item in receipts:
        current = fingerprint(item["path"], full="sha256" in item)
        if current != item:
            raise ValueError(f"Input changed: {item['path']}")


def check(output, inputs=False):
    output = Path(output).resolve()
    provenance = read_json(output / "provenance.json")
    required = {
        "config.json",
        "validation.json",
        "index.html",
        "run_qc.tsv",
        "flags.tsv",
        "thresholds.tsv",
        "scanner_summary.tsv",
        "orphan_mriqc.tsv",
        "methods.md",
    }
    if not required <= set(provenance["outputs"]):
        raise ValueError("Report manifest is incomplete")
    for relative, digest in provenance["outputs"].items():
        path = (output / relative).resolve()
        if output not in path.parents or sha256(path) != digest:
            raise ValueError(f"Report file changed or unsafe path: {relative}")
    if inputs:
        verify_inputs(provenance["inputs"])
        selection = provenance.get("selection")
        rows, metadata = discover(provenance["bids_root"], selection)
        current = {str(p.resolve()) for p in metadata} | {r["bids_path"] for r in rows}
        current |= {
            str(p.resolve())
            for root in provenance["mriqc_roots_in_priority_order"]
            for paths in mriqc_index(root, selection).values()
            for p in paths
        }
        recorded = {r["path"] for r in provenance["inputs"]}
        if not current <= recorded:
            raise ValueError("New BIDS/MRIQC inputs found; rebuild in a new report directory")
    return read_json(output / "validation.json")
