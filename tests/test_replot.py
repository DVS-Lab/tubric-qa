import json
import shutil

import pytest
from conftest import add_image

from tubric_qa.io import read_tsv, sha256
from tubric_qa.pipeline import build, check
from tubric_qa.replot import replot


def test_replot_without_live_inputs_preserves_snapshot(dataset, tmp_path):
    for i in range(6):
        add_image(dataset, subject=f"test{i}")
    add_image(dataset, part="phase")
    _, missing = add_image(dataset, subject="missing")
    missing.unlink()
    source = tmp_path / "source"
    config = tmp_path / "all-panels.json"
    config.write_text(json.dumps({"plot_metrics": None}))
    state = build(dataset[0], [dataset[1]], source, config_path=config)
    hashes = {p.relative_to(source): sha256(p) for p in source.rglob("*") if p.is_file()}
    shutil.rmtree(dataset[0])
    shutil.rmtree(dataset[1])
    output = tmp_path / "simplified"
    assert replot(source, output) == state
    assert check(output) == state
    for name in ("run_qc.tsv", "flags.tsv", "thresholds.tsv", "scanner_summary.tsv",
                 "orphan_mriqc.tsv", "validation.json"):
        assert sha256(output / name) == sha256(source / name)
    assert hashes == {p.relative_to(source): sha256(p) for p in source.rglob("*") if p.is_file()}
    assert len(list((output / "figures").glob("*.png"))) < len(list((source / "figures").glob("*.png")))
    provenance = json.loads((output / "provenance.json").read_text())
    assert not provenance["presentation_refresh"]["live_inputs_checked"]
    assert sha256(output / "source_provenance.json") == sha256(source / "provenance.json")
    with pytest.raises(ValueError, match="already exists"):
        replot(source, output)


def test_tampered_snapshot_refused(dataset, tmp_path, monkeypatch):
    add_image(dataset)
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **k: [])
    source = tmp_path / "source"
    build(dataset[0], [dataset[1]], source)
    with (source / "run_qc.tsv").open("a") as stream:
        stream.write("changed\n")
    with pytest.raises(ValueError, match="Report file changed"):
        replot(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_functional_only_keeps_values_and_removes_only_anatomical_findings(dataset, tmp_path):
    import gzip

    add_image(dataset, subject="func", task="rest", part="mag")
    add_image(dataset, subject="func", task="rest", part="phase")
    anatomy, iqm = add_image(dataset, subject="anat", suffix="T1w")
    iqm.unlink()
    plain = anatomy.with_suffix("")
    plain.write_bytes(gzip.decompress(anatomy.read_bytes()))
    source = tmp_path / "source"
    original = build(dataset[0], [dataset[1]], source)
    assert original["n_identity_or_metadata_issues"] == 2
    assert not original["core_inputs_complete"]
    plain.unlink()  # Simulate the already-verified duplicate cleanup.
    output = tmp_path / "functional"
    state = replot(source, output, functional_only=True)
    assert state["core_inputs_complete"]
    assert state["n_images"] == 2 and state["n_not_applicable"] == 1
    assert state["n_subjects"] == 1
    assert state["selection"] == {"task": ["rest"], "session": []}
    assert not state["exclusion_decisions_made"]
    for name, column in (("run_qc.tsv", "suffix"), ("thresholds.tsv", "suffix"),
                         ("scanner_summary.tsv", "suffix")):
        expected = [row for row in read_tsv(source / name) if row[column] == "bold"]
        assert read_tsv(output / name) == expected
    ids = {row["image_id"] for row in read_tsv(output / "run_qc.tsv")}
    assert read_tsv(output / "flags.tsv") == [r for r in read_tsv(source / "flags.tsv") if r["image_id"] in ids]
    assert check(output, inputs=True) == state
    assert check(source) == original  # Historical artifact validation still passes.
    assert "Functional-only view" in (output / "index.html").read_text()


def test_functional_only_does_not_hide_missing_bold_metrics(dataset, tmp_path):
    _, iqm = add_image(dataset, subject="func")
    iqm.unlink()
    source = tmp_path / "source"
    build(dataset[0], [dataset[1]], source)
    state = replot(source, tmp_path / "functional", functional_only=True)
    assert not state["core_inputs_complete"]
    assert state["n_mriqc_unresolved"] == 1


def test_functional_only_refuses_anatomy_only_report(dataset, tmp_path):
    add_image(dataset, suffix="T1w")
    source = tmp_path / "source"
    build(dataset[0], [dataset[1]], source)
    with pytest.raises(ValueError, match="No images match"):
        replot(source, tmp_path / "functional", functional_only=True)
