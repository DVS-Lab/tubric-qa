from copy import deepcopy
import pytest

from tubric_qa.config import load_config, GROUP_FIELDS
from tubric_qa.statistics import calculate


def records(values, **entities):
    result = []
    for i, value in enumerate(values):
        row = {key: "" for key in GROUP_FIELDS}
        row.update(
            subject=f"s{i}",
            image_id=f"image{i}",
            suffix="bold",
            task="rest",
            session="01",
            scanner_group="A",
            applicable=True,
            validation_issues=[],
            **{m: None for m in load_config()["metrics"]},
        )
        row.update(entities)
        row["fd_mean"] = value
        result.append(row)
    return result


def test_one_pass_flags_not_exclusions():
    rows = records([0.1, 0.2, 0.3, 0.4, 5, 7])
    thresholds, flags, _ = calculate(rows, load_config())
    rule = next(t for t in thresholds if t["metric"] == "fd_mean")
    assert rule["n"] == 6  # Neither extreme is removed to recompute the fence.
    assert len(rows) == 6 and all("excluded" not in r for r in rows)
    assert len([f for f in flags if f["metric"] == "fd_mean"]) == 6


def test_other_sessions_tasks_echoes_versions_do_not_change_thresholds():
    original = records([0.1, 0.2, 0.3, 0.4, 8])
    before = calculate(deepcopy(original), load_config())[0]
    extras = []
    for entity, value in (
        ("session", "02"),
        ("task", "memory"),
        ("echo", "2"),
        ("mriqc_version", "new"),
    ):
        extras.extend(records([100, 200, 300, 400, 500], **{entity: value}))
    after = calculate(deepcopy(original) + extras, load_config())[0]
    for rule in before:
        assert rule == next(
            r
            for r in after
            if r["metric"] == rule["metric"] and r["threshold_group"] == rule["threshold_group"]
        )


@pytest.mark.parametrize("values,status", [([1, 2, 3], "insufficient_n"), ([1] * 5, "zero_iqr")])
def test_no_forced_flags_small_or_zero_iqr(values, status):
    thresholds, flags, _ = calculate(records(values), load_config())
    assert next(t for t in thresholds if t["metric"] == "fd_mean")["status"] == status
    assert all(f["flag"] is None for f in flags)


def test_missing_is_not_false_and_smoothness_descriptive():
    rows = records([0.1, 0.2, 0.3, 0.4, 8, None])
    for row in rows:
        row["fwhm_mean_mm"] = 20
    _, flags, _ = calculate(rows, load_config())
    assert (
        next(f for f in flags if f["metric"] == "fd_mean" and f["image_id"] == "image5")["flag"]
        is None
    )
    assert all(f["status"] == "descriptive_only" for f in flags if f["metric"] == "fwhm_mean_mm")
