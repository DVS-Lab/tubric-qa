import json
import pytest

from conftest import add_image
from tubric_qa.cli import main
from tubric_qa.io import sha256
from tubric_qa.pipeline import build, check


@pytest.fixture
def no_plots(monkeypatch):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *args: [])


def test_end_to_end_real_plots_readonly_and_check(dataset, tmp_path):
    original = []
    for i in range(6):
        original.extend(add_image(dataset, subject=f"test{i}"))
    hashes = {p: sha256(p) for p in original}
    output = tmp_path / "report"
    state = build(dataset[0], [dataset[1]], output, hash_images=True)
    assert state["core_inputs_complete"] and state["n_images"] == 6
    assert not state["exclusion_decisions_made"]
    assert list((output / "figures").glob("*.png"))
    assert "No participant exclusions" in (output / "methods.md").read_text()
    assert check(output, inputs=True) == state
    assert all(sha256(p) == value for p, value in hashes.items())
    with pytest.raises(ValueError, match="already exists"):
        build(dataset[0], [dataset[1]], output)


def test_missing_data_writes_useful_report_strict_exit_two(dataset, tmp_path, no_plots):
    _, iqm = add_image(dataset)
    iqm.unlink()
    output = tmp_path / "report"
    assert (
        main(
            [
                "build",
                "--bids",
                str(dataset[0]),
                "--mriqc",
                str(dataset[1]),
                "--output",
                str(output),
                "--strict",
            ]
        )
        == 2
    )
    assert main(["check", str(output)]) == 0
    assert main(["check", str(output), "--strict"]) == 2


def test_changed_iqm_or_added_image_detected(dataset, tmp_path, no_plots):
    _, iqm = add_image(dataset)
    output = tmp_path / "report"
    build(dataset[0], [dataset[1]], output)
    iqm.write_text('{"tsnr": 10}')
    with pytest.raises(ValueError, match="Input changed"):
        check(output, inputs=True)
    assert check(output)["core_inputs_complete"]


def test_new_input_detected(dataset, tmp_path, no_plots):
    add_image(dataset)
    output = tmp_path / "report"
    build(dataset[0], [dataset[1]], output)
    add_image(dataset, subject="new")
    with pytest.raises(ValueError, match="New BIDS"):
        check(output, inputs=True)


def test_report_tampering_detected(dataset, tmp_path, no_plots):
    add_image(dataset)
    output = tmp_path / "report"
    build(dataset[0], [dataset[1]], output)
    (output / "run_qc.tsv").write_text("tampered")
    with pytest.raises(ValueError, match="Report file changed"):
        check(output)


def test_output_must_not_overlap_inputs(dataset, no_plots):
    add_image(dataset)
    with pytest.raises(ValueError, match="separate"):
        build(dataset[0], [dataset[1]], dataset[0] / "report")


def test_private_metadata_not_copied_and_html_escaped(dataset, tmp_path, no_plots):
    add_image(
        dataset,
        metadata={
            "SoftwareVersions": "<script>alert(1)</script>",
            "PatientName": "Secret Name",
            "PatientBirthDate": "19000101",
        },
    )
    output = tmp_path / "report"
    build(dataset[0], [dataset[1]], output)
    for path in output.rglob("*"):
        if path.is_file() and path.suffix != ".png":
            assert "Secret Name" not in path.read_text()
    assert "<script>" not in (output / "index.html").read_text()


def test_umask_honored(dataset, tmp_path, no_plots):
    import os

    add_image(dataset)
    mask = os.umask(0)
    try:
        output = tmp_path / "report"
        build(dataset[0], [dataset[1]], output)
    finally:
        os.umask(mask)
    assert output.stat().st_mode & 0o777 == 0o777
    assert (output / "run_qc.tsv").stat().st_mode & 0o777 == 0o666


def test_unknown_configuration_rejected(tmp_path):
    from tubric_qa.config import load_config

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"threshold_passes": 2}))
    with pytest.raises(ValueError, match="Unknown"):
        load_config(path)


def test_display_metric_subset_does_not_change_input_completeness(dataset, tmp_path, no_plots):
    from tubric_qa.config import load_config

    add_image(dataset)
    config = load_config()
    config["metrics"] = {"fd_mean": config["metrics"]["fd_mean"]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    state = build(dataset[0], [dataset[1]], tmp_path / "report", config_path=path)
    assert state["core_inputs_complete"]


def test_reserved_metric_name_rejected(tmp_path):
    from tubric_qa.config import load_config

    config = load_config()
    config["metrics"]["applicable"] = config["metrics"]["fd_mean"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="Reserved"):
        load_config(path)
