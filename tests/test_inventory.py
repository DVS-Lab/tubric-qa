import json
import shutil
import pytest

from conftest import add_image
from tubric_qa.config import load_config
from tubric_qa.inventory import discover, attach_mriqc, attach_extras


def collect(dataset):
    rows, _ = discover(dataset[0])
    _, orphans = attach_mriqc(rows, [dataset[1]], load_config())
    return rows, orphans


def test_optional_entities_and_arbitrary_identifiers(dataset):
    add_image(dataset, subject="MixedCaseX", session=None, run=None)
    rows, orphans = collect(dataset)
    (row,) = rows
    assert row["subject"] == "MixedCaseX"
    assert row["session"] == row["run"] == ""
    assert row["mriqc_status"] == "available"
    assert not orphans


def test_echoes_and_phase_never_collapse(dataset):
    add_image(dataset, echo="1", part="mag")
    _, missing = add_image(dataset, echo="2", part="mag")
    missing.unlink()
    add_image(dataset, echo="1", part="phase")
    rows, orphans = collect(dataset)
    assert len(rows) == 3
    assert not orphans
    assert sorted(r["mriqc_status"] for r in rows) == ["available", "missing", "not_applicable"]


def test_inherited_metadata(dataset):
    image, _ = add_image(dataset, metadata={"TaskName": "rest"})
    (dataset[0] / "task-rest_bold.json").write_text(
        json.dumps({"SoftwareVersions": "inherited-X", "Manufacturer": "TestVendor"})
    )
    (row,) = discover(dataset[0])[0]
    assert row["software_version"] == "inherited-X"
    assert row["manufacturer"] == "TestVendor"


def test_duplicate_iqms_not_arbitrarily_selected(dataset):
    _, iqm = add_image(dataset)
    duplicate = dataset[1] / "archive" / iqm.name
    duplicate.parent.mkdir()
    shutil.copyfile(iqm, duplicate)
    rows, _ = collect(dataset)
    assert rows[0]["mriqc_status"] == "ambiguous"
    assert rows[0]["tsnr"] is None


def test_root_priority_is_explicit_and_shadowed_count_recorded(dataset, tmp_path):
    _, iqm = add_image(dataset)
    second = tmp_path / "second"
    second.mkdir()
    shutil.copyfile(iqm, second / iqm.name)
    rows, _ = discover(dataset[0])
    attach_mriqc(rows, [dataset[1], second], load_config())
    assert rows[0]["mriqc_path"] == str(iqm)
    assert rows[0]["shadowed_mriqc_candidates"] == 1


def test_fwhm_uses_each_axis_spacing(dataset):
    add_image(dataset)
    row = collect(dataset)[0][0]
    assert row["fwhm_mean_mm"] == pytest.approx((4 + 6 + 12) / 3)
    assert row["fwhm_z_mm"] == 12


def test_missing_spacing_does_not_guess_units(dataset):
    add_image(dataset, metrics={"tsnr": 40, "fd_mean": 0.1, "fwhm_x": 2, "fwhm_y": 3, "fwhm_z": 4})
    row = collect(dataset)[0][0]
    assert row["fwhm_mean_mm"] is None


@pytest.mark.parametrize("value", ["not-json", "[]", '{"tsnr": "NaN"}'])
def test_invalid_iqm_visible(dataset, value):
    _, iqm = add_image(dataset)
    iqm.write_text(value)
    assert collect(dataset)[0][0]["mriqc_status"] == "invalid"


def test_anatomical_and_orphan(dataset):
    add_image(dataset, suffix="T1w")
    orphan = dataset[1] / "sub-absent_task-rest_bold.json"
    orphan.write_text('{"tsnr": 50}')
    rows, orphans = collect(dataset)
    assert rows[0]["cnr"] == 3 and rows[0]["tsnr"] is None
    assert len(orphans) == 1


def test_extras_exact_identity_and_no_overwrite(dataset, tmp_path):
    image, _ = add_image(dataset)
    rows, _ = collect(dataset)
    config = load_config()
    config["metrics"]["tedana_rejected"] = {
        "label": "Rejected components",
        "unit": "count",
        "direction": "none",
        "modalities": ["bold"],
    }
    path = tmp_path / "extras.tsv"
    path.write_text(
        f"image_id\tmetric_source\ttedana_rejected\n{image.relative_to(dataset[0])}\ttedana 1\t12\n"
    )
    attach_extras(rows, path, config)
    assert rows[0]["tedana_rejected"] == 12
    path.write_text(f"image_id\tmetric_source\ttsnr\n{image.relative_to(dataset[0])}\tother\t12\n")
    with pytest.raises(ValueError, match="cannot replace"):
        attach_extras(rows, path, config)


def test_nonfinite_metrics_never_become_zero(dataset):
    add_image(dataset, metrics={"tsnr": 40, "fd_mean": "NaN", "efc": -1})
    row = collect(dataset)[0][0]
    assert row["fd_mean"] is None and row["efc"] is None


def test_unreadable_header_is_validation_issue(dataset):
    image, _ = add_image(dataset)
    image.write_bytes(b"not nifti")
    assert "unreadable_image_header" in collect(dataset)[0][0]["validation_issues"]


def test_duplicate_extras_columns_rejected(tmp_path):
    from tubric_qa.io import read_tsv

    path = tmp_path / "duplicate.tsv"
    path.write_text("image_id\timage_id\na\tb\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_tsv(path)
