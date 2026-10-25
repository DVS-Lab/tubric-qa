"""Deterministic, explicitly synthetic data for installation and figure checks."""

from pathlib import Path
import nibabel as nib
import numpy as np

from .io import write_json


def generate(destination, subjects=12):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Demo destination exists; choose a new directory")
    if subjects < 6:
        raise ValueError("Demo requires at least six synthetic subjects")
    bids, mriqc = destination / "bids", destination / "mriqc"
    bids.mkdir(parents=True)
    mriqc.mkdir()
    write_json(
        bids / "dataset_description.json",
        {"Name": "SYNTHETIC TUBRIC QA demo", "BIDSVersion": "1.10.0", "DatasetType": "raw"},
    )
    write_json(
        mriqc / "dataset_description.json",
        {
            "Name": "SYNTHETIC MRIQC",
            "BIDSVersion": "1.10.0",
            "DatasetType": "derivative",
            "GeneratedBy": [{"Name": "MRIQC", "Version": "synthetic"}],
        },
    )
    rng = np.random.default_rng(42)
    for i in range(subjects):
        subject = f"demo{i + 1:02}"
        for session in ("baseline", "followup"):
            for task in ("rest", "memory"):
                stem = f"sub-{subject}_ses-{session}_task-{task}_bold"
                directory = bids / f"sub-{subject}/ses-{session}/func"
                directory.mkdir(parents=True, exist_ok=True)
                data = rng.normal(100, 5, (5, 6, 7, 12)).astype("float32")
                image = nib.Nifti1Image(data, np.diag([2, 2, 3, 1]))
                image.header.set_zooms((2, 2, 3, 1.5))
                nib.save(image, directory / (stem + ".nii.gz"))
                write_json(
                    directory / (stem + ".json"),
                    {
                        "TaskName": task,
                        "RepetitionTime": 1.5,
                        "Manufacturer": "SYNTHETIC",
                        "ManufacturersModelName": "Demo scanner",
                        "SoftwareVersions": "Demo-A" if i < subjects // 2 else "Demo-B",
                    },
                )
                out = mriqc / f"sub-{subject}/ses-{session}/func"
                out.mkdir(parents=True, exist_ok=True)
                if i == subjects - 1 and session == "followup" and task == "memory":
                    continue
                offset = 0.3 if i >= subjects // 2 else 0
                write_json(
                    out / (stem + ".json"),
                    {
                        "tsnr": 40 + i,
                        "fd_mean": 0.08 + i * 0.008 if i < subjects - 1 else 1.5,
                        "dvars_std": 1 + i * 0.01,
                        "efc": 0.3 + i * 0.005,
                        "fber": 50 + i,
                        "fwhm_x": 1.6 + offset,
                        "fwhm_y": 1.7 + offset,
                        "fwhm_z": 1.1 + offset,
                        "spacing_x": 2,
                        "spacing_y": 2,
                        "spacing_z": 3,
                        "provenance": {"version": "synthetic"},
                    },
                )
    (destination / "SYNTHETIC.txt").write_text(
        "All images and IQMs are fabricated for software testing, not scientific results.\n"
    )
    return bids, mriqc
