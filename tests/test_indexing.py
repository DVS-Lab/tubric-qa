import json
from pathlib import Path

from bids import BIDSLayout
from bids.layout import BIDSLayoutIndexer
import pytest

from conftest import add_image
from tubric_qa.inventory import discover, input_paths, raw_layout
from tubric_qa.pipeline import build, check


def test_scoped_index_matches_full_metadata_inheritance(dataset):
    bids, _ = dataset
    (bids / "bold.json").write_text(json.dumps({"Manufacturer": "root-vendor"}))
    (bids / "task-rest_bold.json").write_text(json.dumps({"SoftwareVersions": "root-version"}))
    images = []
    for echo in ("1", "2"):
        for part in ("mag", "phase"):
            image, _ = add_image(dataset, session="01", echo=echo, part=part,
                                 metadata={"TaskName": "rest", "RepetitionTime": 1.5})
            images.append(image)
    subject = bids / "sub-abc01"
    (subject / "sub-abc01_task-rest_bold.json").write_text(
        json.dumps({"SoftwareVersions": "subject-version"})
    )
    session = subject / "ses-01"
    (session / "sub-abc01_ses-01_task-rest_bold.json").write_text(
        json.dumps({"ManufacturersModelName": "session-model"})
    )
    sidecar = images[0].with_suffix("").with_suffix(".json")
    sidecar.write_text(json.dumps({"SoftwareVersions": "image-override"}))
    for suffix in ("T1w", "T2w"):
        image, _ = add_image(dataset, suffix=suffix, session="01")
        images.append(image)
    # Unsupported file metadata should not be built, but the file still exists
    # in the filename inventory and the sidecar remains fingerprinted.
    fieldmap, _ = add_image(dataset, suffix="fieldmap", session="01")
    reference = BIDSLayout(bids, validate=False, derivatives=False)
    fast = raw_layout(bids, index_metadata=True)
    for image in images:
        assert fast.get_metadata(str(image)) == reference.get_metadata(str(image))
    assert reference.get_metadata(str(fieldmap))
    assert fast.get_metadata(str(fieldmap)) == {}
    rows, metadata = discover(bids)
    assert set(input_paths(bids)) == {Path(r["bids_path"]) for r in rows} | metadata
    assert sidecar in metadata
    assert (bids / "bold.json") in metadata
    assert fieldmap.with_suffix("").with_suffix(".json") in metadata


def test_check_skips_metadata_and_headers_but_detects_additions(dataset, tmp_path, monkeypatch):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **kw: [])
    add_image(dataset, session="01")
    output = tmp_path / "report"
    state = build(dataset[0], [dataset[1]], output, sessions=["01"])

    def unexpected(*args, **kwargs):
        pytest.fail("Verification rebuilt metadata or reopened image headers")

    monkeypatch.setattr(BIDSLayoutIndexer, "_index_metadata", unexpected)
    monkeypatch.setattr("tubric_qa.inventory.nib.load", unexpected)
    messages = []
    assert check(output, inputs=True, progress=messages.append) == state
    assert any("no metadata re-indexing" in message for message in messages)
    add_image(dataset, session="01", subject="new")
    with pytest.raises(ValueError, match="New BIDS"):
        check(output, inputs=True)


def test_check_detects_new_iqm_and_metadata(dataset, tmp_path, monkeypatch):
    monkeypatch.setattr("tubric_qa.pipeline.figures", lambda *a, **kw: [])
    add_image(dataset)
    output = tmp_path / "report"
    build(dataset[0], [dataset[1]], output)
    new_iqm = dataset[1] / "sub-new_task-rest_bold.json"
    new_iqm.write_text('{"tsnr": 40}')
    with pytest.raises(ValueError, match="New BIDS"):
        check(output, inputs=True)
    new_iqm.unlink()
    (dataset[0] / "task-rest_bold.json").write_text('{"Manufacturer": "new"}')
    with pytest.raises(ValueError, match="New BIDS"):
        check(output, inputs=True)
