import json
import shutil

import pytest
from conftest import add_image

from tubric_qa.io import sha256
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
