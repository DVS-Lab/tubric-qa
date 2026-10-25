"""Offline reports with explicit missingness and task/session-specific plots."""

from collections import defaultdict
from html import escape
import math
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def figures(output, rows, config, thresholds):
    folder = output / "figures"
    folder.mkdir()
    groups = defaultdict(list)
    for row in rows:
        if row["applicable"]:
            groups[row["threshold_group"]].append(row)
    links = []
    for key, group in sorted(groups.items()):
        metrics = [m for m, s in config["metrics"].items() if group[0]["suffix"] in s["modalities"]]
        # Paginate panels to keep arbitrary optional metric sets legible.
        scanners = sorted({r["scanner_group"] for r in group})
        for page in range(math.ceil(len(metrics) / 3)):
            subset = metrics[page * 3 : (page + 1) * 3]
            fig, axes = plt.subplots(
                len(subset),
                2,
                figsize=(13, max(3.3, 0.65 * len(scanners)) * len(subset)),
                squeeze=False,
                constrained_layout=True,
            )
            for i, metric in enumerate(subset):
                spec = config["metrics"][metric]
                members = [r for r in group if r[metric] is not None and not r["validation_issues"]]
                values = [r[metric] for r in members]
                hist, box = axes[i]
                if values:
                    hist.hist(
                        values,
                        bins=min(25, max(1, int(math.sqrt(len(values))))),
                        color="#247d89",
                        edgecolor="white",
                    )
                else:
                    hist.text(
                        0.5, 0.5, "No available measurements", transform=hist.transAxes, ha="center"
                    )
                rule = next(
                    t for t in thresholds if t["threshold_group"] == key and t["metric"] == metric
                )
                if rule["status"] == "estimated":
                    bounds = (
                        [rule["lower_fence"]]
                        if spec["direction"] == "lower"
                        else [rule["upper_fence"]]
                        if spec["direction"] == "upper"
                        else [rule["lower_fence"], rule["upper_fence"]]
                    )
                    for bound in bounds:
                        hist.axvline(bound, color="#b64343", linestyle="--", linewidth=1)
                hist.set(
                    title=f"{spec['label']} ({spec['unit']})",
                    ylabel="Images",
                    xlabel=f"Available {len(values)}/{len(group)}; flag rule: {rule['status']}",
                )
                scanners = sorted({r["scanner_group"] for r in group})
                series = [
                    [r[metric] for r in members if r["scanner_group"] == scanner]
                    for scanner in scanners
                ]
                # Empty groups stay on the axis; no fake zero-valued observations.
                if any(series):
                    result = box.boxplot(
                        [v if v else [np.nan] for v in series],
                        orientation="horizontal",
                        patch_artist=True,
                        widths=0.55,
                    )
                    colors = plt.get_cmap("tab10")
                    for j, patch in enumerate(result["boxes"]):
                        patch.set_facecolor(colors(j % 10))
                        patch.set_alpha(0.5)
                box.set_yticks(range(1, len(scanners) + 1))
                box.set_yticklabels(
                    [textwrap.fill(s, 38) + f"\nn={len(v)}" for s, v in zip(scanners, series)],
                    fontsize=8,
                )
                box.set(
                    xlabel=f"{spec['label']} ({spec['unit']})", title="Scanner/software comparison"
                )
            row = group[0]
            title = f"{row['suffix']} | task {row['task'] or '(none)'} | session {row['session'] or '(none)'}"
            detail = " | ".join(
                f"{f}={row[f]}"
                for f in ("acquisition", "direction", "reconstruction", "echo", "part")
                if row[f]
            )
            fig.suptitle(
                f"{title}\n{detail or 'No additional acquisition entities'} | MRIQC {row['mriqc_version']}\n"
                f"{len(group)} images, {len({r['subject'] for r in group})} participants; review flags are not exclusions",
                fontsize=11,
            )
            name = f"group-{key}-page-{page + 1}.png"
            fig.savefig(folder / name, dpi=120)
            plt.close(fig)
            links.append((title + (" | " + detail if detail else ""), "figures/" + name))
    return links


def html_report(output, rows, config, links, state):
    rows_html = []
    for row in rows:
        missing = [
            m
            for m, spec in config["metrics"].items()
            if row["suffix"] in spec["modalities"] and row.get(m) is None
        ]
        values = (
            row["image_id"],
            row["mriqc_status"],
            row["review_flag_count"],
            ", ".join(missing),
            "; ".join(row["validation_issues"]),
        )
        rows_html.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in values) + "</tr>")
    images = "\n".join(
        f'<section><h2>{escape(label)}</h2><a href="{url}"><img loading="lazy" src="{url}" alt="{escape(label)} QC distributions"></a></section>'
        for label, url in links
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TUBRIC QA | Cohort report</title><style>
body{{font:16px system-ui,sans-serif;color:#202b2c;background:#fff;margin:0}}main{{max-width:1300px;margin:auto;padding:28px}}
h1{{font-size:28px}}h2{{font-size:20px}}p{{max-width:90ch;line-height:1.5}}nav{{padding:12px 0;border-bottom:1px solid #ccc;display:flex;gap:18px;flex-wrap:wrap}}
a{{color:#006e80}}section{{padding:20px 0;border-top:1px solid #ddd}}img{{max-width:100%;height:auto}}.table{{overflow:auto;max-height:600px}}
table{{border-collapse:collapse;font-size:13px;width:100%}}th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:left;overflow-wrap:anywhere}}th{{position:sticky;top:0;background:#edf3f4}}
.status{{padding:12px;background:#edf3f4;border-left:4px solid #247d89}}code{{overflow-wrap:anywhere}}
</style></head><body><main><h1>TUBRIC QA</h1>
<p class="status">{state["n_images"]} images; {state["n_subjects"]} participants; {state["n_mriqc_available"]} MRIQC matches;
{state["n_mriqc_unresolved"]} unresolved MRIQC associations; {state["n_images_flagged"]} images with review flags.</p>
<p>Flags are quantitative review aids, not exclusion decisions. Missing metrics are not passes or zeros.
Thresholds use a single pass within task, session, acquisition, echo and MRIQC-version groups.
Scanner comparisons are descriptive, not causal tests. Image counts can exceed participant counts.</p>
<nav><a href="run_qc.tsv">Image metrics</a><a href="flags.tsv">Flags</a><a href="thresholds.tsv">Thresholds</a>
<a href="scanner_summary.tsv">Scanner summary</a><a href="validation.json">Validation</a><a href="methods.md">Methods</a></nav>
<section><h2>Input completeness</h2><div class="table"><table><thead><tr><th>Image</th><th>MRIQC association</th><th>Flags</th><th>Missing metrics</th><th>Validation issues</th></tr></thead>
<tbody>{"".join(rows_html)}</tbody></table></div></section>{images}
<footer><p>Contains study identifiers. Review before sharing; this report is not a de-identification tool. No external scripts, fonts or network requests.</p></footer>
</main></body></html>"""
    (output / "index.html").write_text(page, encoding="utf-8")


def methods(output, config):
    (output / "methods.md").write_text(
        "# Methods\n\nRaw BIDS inputs were indexed with PyBIDS, including metadata inheritance. "
        "BOLD, T1w and T2w magnitude images were matched to MRIQC IQM JSONs by exact BIDS entities. "
        "Sessions and run numbers were never inferred. Each echo remains a separate image. "
        "Phase/real/imaginary images are listed but not used for these IQMs.\n\n"
        "MRIQC values retain their own processing-stage meaning; they are not metrics of final "
        "fMRIPrep/FEAT images. FWHM is converted from voxel units independently for each axis using "
        "MRIQC spacing, then averaged arithmetically in mm (not geometric combined FWHM). "
        "Missing spacing produces missing mm FWHM, not a guessed conversion.\n\n"
        f"Review fences use linear quartiles and {config['iqr_multiplier']:g} times the IQR, "
        f"with at least {config['min_n']} valid observations. All metrics are evaluated independently "
        "in one pass; flagged images are not removed before estimating another fence. Groups with "
        "zero IQR or insufficient observations are not classified. Smoothness is descriptive by "
        "default. No participant exclusions or selected-cohort files are generated.\n\n"
        "Software labels default to exact header strings. User-supplied exact aliases, additional "
        "grouping fields and metric directions are saved in config.json. No scanner-era inference "
        "from acquisition dates is performed. Unknown metadata remains visible.\n\n"
        "References: [MRIQC IQMs](https://mriqc.readthedocs.io/en/stable/iqms/bold.html); "
        "[MRIQC](https://doi.org/10.1371/journal.pone.0184661); "
        "[PyBIDS](https://bids-standard.github.io/pybids/).\n",
        encoding="utf-8",
    )
