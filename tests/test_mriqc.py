from types import SimpleNamespace
import pytest

from conftest import add_image
from tubric_qa.mriqc import prepare, launch


def options(dataset, tmp_path, **overrides):
    values = dict(
        bids=dataset[0],
        existing=[dataset[1]],
        output=tmp_path / "new-mriqc",
        work_dir=tmp_path / "work",
        engine="docker",
        image="nipreps/mriqc:24.0.2",
        executable="mriqc",
        nprocs=4,
        threads=1,
        mem_gb=8,
        execute=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_plan_no_writes_no_upload_and_bounded(dataset, tmp_path):
    _, iqm = add_image(dataset)
    iqm.unlink()
    args = options(dataset, tmp_path)
    result = prepare(args)
    command = result["command"]
    assert "--no-sub" in command and "--notrack" in command
    assert "--nprocs" in command and "--mem" in command
    assert any("readonly" in item for item in command)
    assert launch(args) == 0
    assert not args.output.exists() and not args.work_dir.exists()


def test_nothing_to_run_preserves_existing(dataset, tmp_path):
    add_image(dataset)
    assert prepare(options(dataset, tmp_path))["command"] == []


@pytest.mark.parametrize(
    "overrides", [{"image": "nipreps/mriqc:latest"}, {"threads": 8}, {"mem_gb": 0}]
)
def test_unsafe_settings_rejected(dataset, tmp_path, overrides):
    _, iqm = add_image(dataset)
    iqm.unlink()
    with pytest.raises(ValueError):
        prepare(options(dataset, tmp_path, **overrides))


def test_only_missing_subjects_planned(dataset, tmp_path):
    add_image(dataset, subject="complete")
    _, iqm = add_image(dataset, subject="missing")
    iqm.unlink()
    assert prepare(options(dataset, tmp_path))["subjects"] == ["missing"]


def test_apptainer_and_native_plans(dataset, tmp_path):
    _, iqm = add_image(dataset)
    iqm.unlink()
    sif = tmp_path / "mriqc.sif"
    sif.write_bytes(b"test")
    command = prepare(options(dataset, tmp_path, engine="apptainer", image=str(sif)))["command"]
    assert command[:3] == ["apptainer", "run", "--cleanenv"]
    assert "--containall" in command
    command = prepare(options(dataset, tmp_path, engine="native"))["command"]
    assert command[0] == "mriqc" and command[1] == str(dataset[0])


def test_native_execution_receipt_and_failure_preservation(dataset, tmp_path, monkeypatch):
    import json

    _, iqm = add_image(dataset)
    iqm.unlink()
    args = options(dataset, tmp_path, engine="native", execute=True)
    executable = tmp_path / "fake-mriqc"
    executable.write_text("synthetic executable")
    monkeypatch.setattr("tubric_qa.mriqc.shutil.which", lambda command: str(executable))
    monkeypatch.setattr(
        "tubric_qa.mriqc.subprocess.check_output", lambda *a, **k: "synthetic-version"
    )
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr("tubric_qa.mriqc.subprocess.run", execute)
    assert launch(args) == 7
    receipt = json.loads((args.output / "tubric-qa-launch.json").read_text())
    assert receipt["exit_code"] == 7 and receipt["mriqc_version"] == "synthetic-version"
    assert len(calls) == 1
    with pytest.raises(ValueError, match="already exists"):
        launch(args)
