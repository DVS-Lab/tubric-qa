"""Metric units and review rules; no study-specific thresholds or decisions."""

from copy import deepcopy
from .io import finite, read_json


# MRIQC functional FWHM is in voxel units. Convert each axis with its own spacing.
METRICS = {
    "tsnr": {
        "label": "Temporal SNR",
        "unit": "ratio",
        "direction": "lower",
        "modalities": ["bold"],
    },
    "fd_mean": {
        "label": "Mean framewise displacement",
        "unit": "mm",
        "direction": "upper",
        "modalities": ["bold"],
    },
    "dvars_std": {
        "label": "Standardized DVARS",
        "unit": "ratio",
        "direction": "upper",
        "modalities": ["bold"],
    },
    "fwhm_mean_mm": {
        "label": "MRIQC mean directional FWHM",
        "unit": "mm",
        "direction": "none",
        "modalities": ["bold", "T1w", "T2w"],
    },
    "efc": {
        "label": "Entropy focus criterion",
        "unit": "ratio",
        "direction": "upper",
        "modalities": ["bold", "T1w", "T2w"],
    },
    "fber": {
        "label": "Foreground/background energy",
        "unit": "ratio",
        "direction": "lower",
        "modalities": ["bold", "T1w", "T2w"],
    },
    "cnr": {
        "label": "Contrast-to-noise ratio",
        "unit": "ratio",
        "direction": "lower",
        "modalities": ["T1w", "T2w"],
    },
    "cjv": {
        "label": "Coefficient of joint variation",
        "unit": "ratio",
        "direction": "upper",
        "modalities": ["T1w", "T2w"],
    },
}
GROUP_FIELDS = [
    "suffix",
    "task",
    "session",
    "acquisition",
    "direction",
    "reconstruction",
    "echo",
    "part",
    "mriqc_version",
]
DEFAULT = {
    "schema_version": 1,
    "iqr_multiplier": 1.5,
    "min_n": 5,
    "additional_group_fields": [],
    "software_labels": {},
    "plot_metrics": ["fwhm_mean_mm", "tsnr", "fd_mean"],
    "metrics": METRICS,
}


def load_config(path=None):
    result = deepcopy(DEFAULT)
    if path:
        supplied = read_json(path)
        unknown = set(supplied) - set(DEFAULT)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        result.update(supplied)
    if result["schema_version"] != 1:
        raise ValueError("Unsupported configuration schema")
    number = finite(result["iqr_multiplier"])
    if number is None or number <= 0:
        raise ValueError("iqr_multiplier must be positive")
    result["iqr_multiplier"] = number
    if type(result["min_n"]) is not int or result["min_n"] < 4:
        raise ValueError("min_n must be an integer >= 4")
    if not isinstance(result["additional_group_fields"], list) or any(
        key not in ("manufacturer", "model", "software_version", "scanner_group")
        for key in result["additional_group_fields"]
    ):
        raise ValueError("Unsupported additional_group_fields")
    if not isinstance(result["software_labels"], dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v
        for k, v in result["software_labels"].items()
    ):
        raise ValueError("software_labels must map exact strings to nonempty labels")
    if not isinstance(result["metrics"], dict) or not result["metrics"]:
        raise ValueError("metrics must be a nonempty object")
    plotted = result["plot_metrics"]
    if plotted is not None and (
        not isinstance(plotted, list)
        or not plotted
        or any(not isinstance(key, str) or key not in (METRICS | result["metrics"]) for key in plotted)
        or len(set(plotted)) != len(plotted)
    ):
        raise ValueError("plot_metrics must be null or a nonempty list of unique known metrics")
    for key, metric in result["metrics"].items():
        reserved = set(GROUP_FIELDS) | {
            "subject",
            "run",
            "ceagent",
            "chunk",
            "image_id",
            "bids_path",
            "image_shape",
            "manufacturer",
            "model",
            "software_version",
            "software_label",
            "scanner_group",
            "applicable",
            "validation_issues",
            "metadata_status",
            "mriqc_status",
            "mriqc_path",
            "shadowed_mriqc_candidates",
            "extra_metric_source",
            "threshold_group",
            "review_flag_count",
        }
        if key in reserved:
            raise ValueError(f"Reserved metric name: {key}")
        if not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"Invalid metric name: {key}")
        if set(metric) != {"label", "unit", "direction", "modalities"}:
            raise ValueError(f"Metric {key} requires label/unit/direction/modalities")
        if metric["direction"] not in ("upper", "lower", "both", "none"):
            raise ValueError(f"Invalid metric direction: {key}")
        if (
            not isinstance(metric["modalities"], list)
            or not metric["modalities"]
            or any(item not in ("bold", "T1w", "T2w") for item in metric["modalities"])
        ):
            raise ValueError(f"Invalid modalities: {key}")
        if not all(isinstance(metric[k], str) and metric[k] for k in ("label", "unit")):
            raise ValueError(f"Invalid label/unit: {key}")
    return result
