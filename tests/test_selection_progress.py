import json
import threading

import pytest

from conftest import add_image
from tubric_qa.cli import main
from tubric_qa.inventory import normalize_selection
from tubric_qa.io import read_tsv
from tubric_qa.pipeline import build, check
from tubric_qa.progress import Progress


def test_selection_preserves_groups_and_excludes_other_headers(dataset, tmp_path, monkeypatch):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **kw: [])
    for session in ("01", "02"):
        for task in ("doors", "ugr"):
            for i in range(6):
                add_image(dataset, subject=f"s{i}", session=session, task=task,
                          metrics={"tsnr": 20 + i, "fd_mean": i / 10})
    add_image(dataset, session="01", suffix="T1w")
    full = tmp_path / "full"
    build(dataset[0], [dataset[1]], full)
    import tubric_qa.inventory as inventory
    original_load = inventory.nib.load
    opened = []

    def load(path):
        opened.append(str(path))
        return original_load(path)

    monkeypatch.setattr(inventory.nib, "load", load)
    output = tmp_path / "selected"
    state = build(dataset[0], [dataset[1]], output, tasks=["doors"], sessions=["ses-01"])
    assert state["n_images"] == 6
    assert state["n_orphan_mriqc"] == 0
    assert all("ses-01" in p and "task-doors" in p for p in opened)
    assert check(output, inputs=True) == state
    assert json.loads((output / "provenance.json").read_text())["selection"] == {
        "task": ["doors"], "session": ["01"],
    }
    full_rows = {r["image_id"]: r for r in read_tsv(full / "run_qc.tsv")}
    for row in read_tsv(output / "run_qc.tsv"):
        assert row == full_rows[row["image_id"]]
    full_thresholds = read_tsv(full / "thresholds.tsv")
    assert all(row in full_thresholds for row in read_tsv(output / "thresholds.tsv"))


def test_repeated_filters_and_no_match(dataset, tmp_path, monkeypatch):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **kw: [])
    add_image(dataset, task="doors", session="01")
    add_image(dataset, task="ugr", session="02")
    add_image(dataset, task="rest")
    state = build(dataset[0], [dataset[1]], tmp_path / "both",
                  tasks=["task-doors", "ugr"], sessions=["01", "02"])
    assert state["n_images"] == 2
    with pytest.raises(ValueError, match="No BOLD"):
        build(dataset[0], [dataset[1]], tmp_path / "empty", tasks=["missing"])
    assert not (tmp_path / "empty").exists()
    with pytest.raises(ValueError, match="Invalid session"):
        normalize_selection(sessions=["*"])


def test_cli_progress_quiet_and_no_mriqc_launch(dataset, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **kw: [])
    monkeypatch.setattr("tubric_qa.mriqc.launch", lambda *a: pytest.fail("MRIQC launched"))
    add_image(dataset, task="ugr", session="01")
    args = ["build", "--bids", str(dataset[0]), "--mriqc", str(dataset[1]),
            "--task", "ugr", "--session", "01", "--output"]
    assert main([*args, str(tmp_path / "loud")]) == 0
    captured = capsys.readouterr()
    assert "MRIQC will not be launched" in captured.err
    assert "Indexing BIDS" in captured.err
    assert "Report complete" in captured.err
    assert main([*args, str(tmp_path / "quiet"), "--quiet"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Report:" in captured.out


def test_heartbeat_stops_on_error(monkeypatch):
    seen = threading.Event()
    messages = []
    progress = Progress(interval=0.01)

    def write(message):
        messages.append(message)
        if "Still working" in message:
            seen.set()

    monkeypatch.setattr(progress, "_write", write)
    with pytest.raises(ValueError):
        with progress:
            progress("Indexing")
            assert seen.wait(2)
            raise ValueError("test")
    assert not progress.thread.is_alive()
    assert "Still working: Indexing" in messages


def test_old_report_without_selection_still_checks(dataset, tmp_path, monkeypatch):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **kw: [])
    add_image(dataset)
    output = tmp_path / "old"
    build(dataset[0], [dataset[1]], output)
    path = output / "provenance.json"
    provenance = json.loads(path.read_text())
    del provenance["selection"]
    path.write_text(json.dumps(provenance))
    assert check(output, inputs=True)["core_inputs_complete"]
