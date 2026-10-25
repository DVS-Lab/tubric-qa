"""Explicit, resource-bounded MRIQC launch plans; no implicit execution/upload."""

from pathlib import Path
import os
import shlex
import shutil
import subprocess

from .config import load_config
from .inventory import discover, attach_mriqc
from .io import disjoint_output, sha256, write_json


def prepare(args):
    bids = args.bids.resolve()
    output = disjoint_output(args.output, [bids, *args.existing])
    work = disjoint_output(args.work_dir, [bids, output, *args.existing])
    rows, _ = discover(bids)
    attach_mriqc(rows, args.existing, load_config())
    if any(r["validation_issues"] or r["mriqc_status"] == "ambiguous" for r in rows):
        raise ValueError(
            "Resolve input identity/metadata and ambiguous MRIQC matches before launching"
        )
    missing = [r for r in rows if r["applicable"] and r["mriqc_status"] != "available"]
    subjects = sorted({r["subject"] for r in missing})
    if args.nprocs < 1 or not 1 <= args.threads <= args.nprocs or args.mem_gb <= 0:
        raise ValueError("Require nprocs >= threads >= 1 and positive mem-gb")
    if not subjects:
        return {
            "subjects": [],
            "command": [],
            "note": "MRIQC associations already available; nothing launched",
        }
    modalities = sorted({r["suffix"] for r in missing})
    if args.engine == "native":
        prefix, locations = [args.executable], [str(bids), str(output), str(work)]
    else:
        if not args.image:
            raise ValueError(
                "Container engine requires --image (explicit Docker tag/digest or local SIF)"
            )
        for path in (bids, output, work):
            if any(char in str(path) for char in (",", ":", "\n")):
                raise ValueError("Container bind paths cannot contain comma, colon or newline")
        locations = ["/data", "/out", "/work"]
        if args.engine == "docker":
            if args.image.endswith(":latest") or (
                ":" not in args.image and "@sha256:" not in args.image
            ):
                raise ValueError("Use a pinned MRIQC image tag or digest, not latest")
            prefix = [
                "docker",
                "run",
                "--rm",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--mount",
                f"type=bind,src={bids},dst=/data,readonly",
                "--mount",
                f"type=bind,src={output},dst=/out",
                "--mount",
                f"type=bind,src={work},dst=/work",
                args.image,
            ]
        else:
            image = Path(args.image).resolve()
            if not image.is_file():
                raise ValueError("Apptainer --image must name an existing local SIF")
            prefix = [
                "apptainer",
                "run",
                "--cleanenv",
                "--containall",
                "--bind",
                f"{bids}:/data:ro",
                "--bind",
                f"{output}:/out",
                "--bind",
                f"{work}:/work",
                str(image),
            ]
    data_path, out_path, work_path = locations
    command = [
        *prefix,
        data_path,
        out_path,
        "participant",
        "--participant-label",
        *subjects,
        "-m",
        *modalities,
        "--no-sub",
        "--notrack",
        "--nprocs",
        str(args.nprocs),
        "--omp-nthreads",
        str(args.threads),
        "--mem",
        str(args.mem_gb),
        "-w",
        work_path,
    ]
    return {
        "subjects": subjects,
        "missing_images": [r["image_id"] for r in missing],
        "command": command,
        "engine": args.engine,
        "note": "Selected subjects/modalities run in a fresh output. Existing IQMs are untouched. Some already-measured images in these subjects may be recomputed; prefer the existing root first when building reports.",
    }


def launch(args):
    plan = prepare(args)
    print(plan["note"])
    if not plan["command"]:
        return 0
    print("Command:", shlex.join(plan["command"]))
    if not args.execute:
        print("PLAN ONLY. Add --execute to run MRIQC; no directories or data changed.")
        return 0
    if not shutil.which(plan["command"][0]):
        raise ValueError(f"Executable not found: {plan['command'][0]}")
    # Resolve the actual installed image identity before execution; no implicit pull.
    if args.engine == "docker":
        image_id = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", args.image], text=True
        ).strip()
        if not image_id.startswith("sha256:"):
            raise ValueError("Cannot resolve installed Docker image ID; explicitly pull it first")
        plan["image_id"] = image_id
        plan["command"][plan["command"].index(args.image)] = image_id
    elif args.engine == "apptainer":
        plan["image_sha256"] = sha256(args.image)
    else:
        plan["mriqc_version"] = subprocess.check_output(
            [args.executable, "--version"], text=True
        ).strip()
        plan["executable_sha256"] = sha256(shutil.which(args.executable))
    args.output.mkdir(parents=True, exist_ok=False)
    args.work_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "tubric-qa-launch.json", plan)
    with (args.output / "tubric-qa-mriqc.log").open("w") as stream:
        process = subprocess.run(
            plan["command"],
            stdout=stream,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "OMP_NUM_THREADS": str(args.threads),
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
        )
    plan["exit_code"] = process.returncode
    write_json(args.output / "tubric-qa-launch.json", plan)
    print(f"MRIQC exit: {process.returncode}; log: {args.output / 'tubric-qa-mriqc.log'}")
    print(
        "Run tubric-qa build to validate image/IQM completeness; exit 0 alone does not establish completeness."
    )
    return process.returncode
