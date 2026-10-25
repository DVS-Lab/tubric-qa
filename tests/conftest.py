from pathlib import Path
import json
import nibabel as nib
import numpy as np
import pytest


@pytest.fixture
def dataset(tmp_path):
    bids, mriqc = tmp_path / "bids", tmp_path / "mriqc"
    bids.mkdir()
    mriqc.mkdir()
    (bids / "dataset_description.json").write_text(
        json.dumps({"Name": "Synthetic", "BIDSVersion": "1.10.0"})
    )
    return bids, mriqc


def add_image(
    dataset,
    subject="abc01",
    session=None,
    task="rest",
    run=None,
    echo=None,
    part=None,
    suffix="bold",
    acquisition=None,
    metrics=None,
    metadata=None,
):
    bids, mriqc = dataset
    tokens = [f"sub-{subject}"]
    folder = Path(f"sub-{subject}")
    if session:
        tokens.append(f"ses-{session}")
        folder /= f"ses-{session}"
    folder /= "func" if suffix == "bold" else "anat"
    if suffix == "bold":
        tokens.append(f"task-{task}")
    for key, value in (("acq", acquisition), ("run", run), ("echo", echo), ("part", part)):
        if value:
            tokens.append(f"{key}-{value}")
    stem = "_".join([*tokens, suffix])
    directory = bids / folder
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / (stem + ".nii.gz")
    nib.save(
        nib.Nifti1Image(
            np.ones((3, 4, 5, 6) if suffix == "bold" else (3, 4, 5), dtype="float32"), np.eye(4)
        ),
        image,
    )
    (directory / (stem + ".json")).write_text(
        json.dumps(
            metadata or {"SoftwareVersions": "software-A", "TaskName": task, "RepetitionTime": 1.5}
        )
    )
    iqm_dir = mriqc / folder
    iqm_dir.mkdir(parents=True, exist_ok=True)
    iqm = iqm_dir / (stem + ".json")
    iqm.write_text(
        json.dumps(
            metrics
            if metrics is not None
            else {
                "tsnr": 40,
                "fd_mean": 0.1,
                "dvars_std": 1.1,
                "efc": 0.3,
                "cjv": 0.4,
                "cnr": 3,
                "fber": 30,
                "fwhm_x": 2,
                "fwhm_y": 3,
                "fwhm_z": 4,
                "spacing_x": 2,
                "spacing_y": 2,
                "spacing_z": 3,
                "provenance": {"version": "24-test"},
            }
        )
    )
    return image, iqm
