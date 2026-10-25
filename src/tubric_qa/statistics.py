"""One-pass, independent review flags, never a selection pipeline."""

from collections import defaultdict
import hashlib
import json

import numpy as np

from .config import GROUP_FIELDS


def group_id(key):
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]


def calculate(rows, config):
    fields = GROUP_FIELDS + config["additional_group_fields"]
    groups = defaultdict(list)
    for row in rows:
        row["review_flag_count"] = 0
        if row["applicable"]:
            key = tuple(row.get(field, "") for field in fields)
            row["threshold_group"] = group_id(key)
            groups[key].append(row)
    thresholds, flags, summary = [], [], []
    for key, group in sorted(groups.items()):
        for metric, spec in config["metrics"].items():
            if group[0]["suffix"] not in spec["modalities"]:
                continue
            values = [
                r[metric] for r in group if r[metric] is not None and not r["validation_issues"]
            ]
            base = {
                **dict(zip(fields, key)),
                "threshold_group": group_id(key),
                "metric": metric,
                "unit": spec["unit"],
                "direction": spec["direction"],
                "n": len(values),
                "n_images": len(group),
                "n_subjects": len({r["subject"] for r in group}),
                "q1": None,
                "median": None,
                "q3": None,
                "lower_fence": None,
                "upper_fence": None,
                "status": "insufficient_n",
                "n_flagged": 0,
            }
            if values:
                q1, median, q3 = map(float, np.quantile(values, [0.25, 0.5, 0.75], method="linear"))
                base.update(q1=q1, median=median, q3=q3)
                if spec["direction"] == "none":
                    base["status"] = "descriptive_only"
                elif len(values) >= config["min_n"]:
                    if q3 == q1:
                        base["status"] = "zero_iqr"
                    else:
                        base.update(
                            status="estimated",
                            lower_fence=q1 - config["iqr_multiplier"] * (q3 - q1),
                            upper_fence=q3 + config["iqr_multiplier"] * (q3 - q1),
                        )
            for row in group:
                value, flag = row[metric], None
                status = base["status"]
                if row["validation_issues"]:
                    status = "invalid_input_identity"
                elif value is None:
                    status = "missing_metric"
                elif base["status"] == "estimated":
                    flag = (
                        spec["direction"] in ("lower", "both") and value < base["lower_fence"]
                    ) or (spec["direction"] in ("upper", "both") and value > base["upper_fence"])
                    status = "flagged" if flag else "within_fence"
                    row["review_flag_count"] += int(flag)
                    base["n_flagged"] += int(flag)
                flags.append(
                    {
                        "image_id": row["image_id"],
                        "threshold_group": group_id(key),
                        "metric": metric,
                        "value": value,
                        "flag": flag,
                        "status": status,
                    }
                )
            thresholds.append(base)
            for scanner in sorted({r["scanner_group"] for r in group}):
                members = [r for r in group if r["scanner_group"] == scanner]
                vals = [
                    r[metric]
                    for r in members
                    if r[metric] is not None and not r["validation_issues"]
                ]
                summary.append(
                    {
                        **dict(zip(fields, key)),
                        "threshold_group": group_id(key),
                        "scanner_group": scanner,
                        "metric": metric,
                        "unit": spec["unit"],
                        "n_images": len(members),
                        "n_values": len(vals),
                        "n_subjects": len({r["subject"] for r in members}),
                        "n_missing_or_invalid": len(members) - len(vals),
                        **{
                            name: float(np.quantile(vals, q)) if vals else None
                            for name, q in (
                                ("q1", 0.25),
                                ("median", 0.5),
                                ("q3", 0.75),
                                ("p95", 0.95),
                                ("maximum", 1),
                            )
                        },
                    }
                )
    return thresholds, flags, summary
