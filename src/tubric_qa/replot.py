"""Render a verified report snapshot without reading live imaging inputs."""

from datetime import datetime, timezone
import csv
import importlib.metadata
from pathlib import Path
import os
import shutil
import tempfile

from . import __version__
from .config import DEFAULT, load_config
from .inventory import entities
from .io import disjoint_output, finite, read_json, read_tsv, sha256, write_json, write_tsv
from .pipeline import check, validation_state
from .report import figures, html_report


def replot(source, output, progress=None, *, functional_only=False):
    progress = progress or (lambda message: None)
    source = Path(source).resolve()
    progress("Verifying saved report; no BIDS/MRIQC indexing or live-input checks")
    source_digest = sha256(source / "provenance.json")
    state = check(source)
    provenance = read_json(source / "provenance.json")
    output = disjoint_output(output, [source, provenance["bids_root"],
                                      *provenance["mriqc_roots_in_priority_order"]])
    config = load_config(source / "config.json")
    config["plot_metrics"] = list(DEFAULT["plot_metrics"])
    progress("Loading saved image metrics and thresholds; no recalculation")
    saved_rows = read_tsv(source / "run_qc.tsv")
    rows = [dict(row) for row in saved_rows if not functional_only or row["suffix"] == "bold"]
    if not rows:
        raise ValueError("No images match the report selection")
    for row in rows:
        if row["applicable"] not in ("True", "False"):
            raise ValueError("Invalid saved applicability value")
        row["applicable"] = row["applicable"] == "True"
        row["validation_issues"] = row["validation_issues"].split(";") if row["validation_issues"] else []
        row["review_flag_count"] = int(row["review_flag_count"])
        for metric in config["metrics"]:
            row[metric] = finite(row[metric])
    thresholds = read_tsv(source / "thresholds.tsv")
    if functional_only:
        thresholds = [row for row in thresholds if row["suffix"] == "bold"]
    for rule in thresholds:
        for field in ("lower_fence", "upper_fence"):
            rule[field] = finite(rule.get(field))

    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".tubric-qa-replot-", dir=output.parent))
    mask = os.umask(0)
    os.umask(mask)
    stage.chmod(0o777 & ~mask)
    try:
        # Retained QC values/rules are never recalculated, even for a filtered view.
        for name in ("run_qc.tsv", "flags.tsv", "thresholds.tsv", "scanner_summary.tsv",
                     "orphan_mriqc.tsv", "validation.json", "methods.md"):
            shutil.copyfile(source / name, stage / name)
        if functional_only:
            if any(not row["task"] for row in rows):
                raise ValueError("Functional selection requires explicit task identities")
            selection = {"task": sorted({row["task"] for row in rows}),
                         "session": provenance.get("selection", {}).get("session", [])}
            selected_ids = {row["image_id"] for row in rows}
            filtered = {
                "run_qc.tsv": [r for r in saved_rows if r["image_id"] in selected_ids],
                "flags.tsv": [r for r in read_tsv(source / "flags.tsv") if r["image_id"] in selected_ids],
                "thresholds.tsv": [r for r in read_tsv(source / "thresholds.tsv") if r["suffix"] == "bold"],
                "scanner_summary.tsv": [r for r in read_tsv(source / "scanner_summary.tsv") if r["suffix"] == "bold"],
                "orphan_mriqc.tsv": [r for r in read_tsv(source / "orphan_mriqc.tsv")
                                     if entities(Path(r["mriqc_path"]))["suffix"] == "bold"],
            }
            for name, entries in filtered.items():
                with (source / name).open(newline="", encoding="utf-8") as stream:
                    fields = next(csv.reader(stream, delimiter="\t"))
                write_tsv(stage / name, entries, fields)
            state = validation_state(rows, filtered["orphan_mriqc.tsv"], selection)
            write_json(stage / "validation.json", state)
            # Drop only omitted image receipts; retain conservative metadata/IQM lineage.
            omitted = {str(Path(provenance["bids_root"]) / r["image_id"])
                       for r in saved_rows if r["image_id"] not in selected_ids}
            provenance["inputs"] = [r for r in provenance["inputs"] if r["path"] not in omitted]
            provenance["selection"] = selection
        shutil.copyfile(source / "provenance.json", stage / "source_provenance.json")
        write_json(stage / "config.json", config)
        links = figures(stage, rows, config, thresholds, progress=progress)
        html_report(stage, rows, config, links, state, scope_notice=(
            "Functional-only view of a verified saved report. Anatomical images are outside this "
            "report's scope. Live inputs were not rechecked; no MRIQC processing or exclusion "
            "decisions were changed."
            if functional_only else "Saved report replotted; live inputs were not rechecked."
        ))
        with (stage / "methods.md").open("a", encoding="utf-8") as stream:
            stream.write("\n## Presentation-only refresh\n\n"
                         "Plots were regenerated from the verified saved tables, showing smoothness, "
                         "tSNR and mean FD where applicable. "
                         + ("Only BOLD rows are included. Retained values, thresholds and flags are "
                            "unchanged; completeness counts were recomputed for this functional-only scope. "
                            if functional_only else
                            "Tables, thresholds, flags and validation state were copied unchanged. ")
                         + "Live imaging inputs were not checked again. "
                         "Original analysis provenance is saved in source_provenance.json.\n")
        write_json(stage / "report_scope.json", {
            "functional_only": functional_only,
            "source_report": str(source),
            "live_inputs_checked": False,
            "notice": "Saved-snapshot view; no processing or exclusion decisions changed.",
        })
        provenance["presentation_refresh"] = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "version": __version__,
            "source_report": str(source),
            "source_provenance_sha256": source_digest,
            "live_inputs_checked": False,
            "functional_only": functional_only,
            "dependencies": {name: importlib.metadata.version(name)
                             for name in ("pybids", "numpy", "matplotlib", "nibabel")},
            "code_sha256": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")},
        }
        provenance["outputs"] = {
            p.relative_to(stage).as_posix(): sha256(p)
            for p in sorted(stage.rglob("*")) if p.is_file()
        }
        write_json(stage / "provenance.json", provenance)
        check(source)
        if sha256(source / "provenance.json") != source_digest:
            raise ValueError("Source report provenance changed during replot")
        check(stage)
        if output.exists():
            raise ValueError("Output appeared during replot; refusing to replace it")
        stage.rename(output)
    except BaseException:
        shutil.rmtree(stage)
        raise
    progress(f"Replot complete: {len(links)} figures; original report and retained QC values unchanged")
    return state
