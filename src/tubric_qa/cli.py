"""Command line entry points."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import __version__
from .config import DEFAULT
from .demo import generate
from .mriqc import launch
from .pipeline import build, check


def parser():
    cli = argparse.ArgumentParser(
        description="Portable BIDS/MRIQC QC reports. Flags are not exclusions."
    )
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command", required=True)
    report = commands.add_parser("build", help="Create a new, offline QC report")
    report.add_argument("--bids", type=Path, required=True)
    report.add_argument(
        "--mriqc",
        type=Path,
        action="append",
        required=True,
        help="Repeat for fallback roots; first matching root wins, with shadowed counts recorded",
    )
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--config", type=Path)
    report.add_argument(
        "--extras", type=Path, help="Optional configured numeric metrics keyed by exact image_id"
    )
    report.add_argument(
        "--hash-images",
        action="store_true",
        help="Full source NIfTI SHA256 rather than size/mtime (slower)",
    )
    report.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 if core MRIQC/identity inputs are incomplete; still writes report",
    )
    verify = commands.add_parser(
        "check", help="Verify report hashes; optionally verify live inputs"
    )
    verify.add_argument("output", type=Path)
    verify.add_argument("--inputs", action="store_true")
    verify.add_argument("--strict", action="store_true")
    commands.add_parser("config", help="Print the complete default configuration JSON")
    demo = commands.add_parser("demo", help="Create explicitly synthetic BIDS/MRIQC data")
    demo.add_argument("destination", type=Path)
    demo.add_argument("--subjects", type=int, default=12)
    mriqc = commands.add_parser(
        "mriqc", help="Plan or explicitly launch MRIQC into a fresh directory"
    )
    mriqc.add_argument("--bids", type=Path, required=True)
    mriqc.add_argument("--existing", type=Path, action="append", default=[])
    mriqc.add_argument("--output", type=Path, required=True)
    mriqc.add_argument("--work-dir", type=Path, required=True)
    mriqc.add_argument("--engine", choices=("docker", "apptainer", "native"), default="docker")
    mriqc.add_argument("--image", help="Explicit Docker tag/digest or local Apptainer SIF")
    mriqc.add_argument("--executable", default="mriqc", help="Native MRIQC executable")
    mriqc.add_argument("--nprocs", type=int, default=4)
    mriqc.add_argument("--threads", type=int, default=1)
    mriqc.add_argument("--mem-gb", type=float, default=8)
    mriqc.add_argument(
        "--execute", action="store_true", help="Actually run the displayed MRIQC plan"
    )
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "config":
            print(json.dumps(DEFAULT, indent=2))
            return 0
        if args.command == "demo":
            bids, mriqc = generate(args.destination, args.subjects)
            print(f"SYNTHETIC demo created. BIDS: {bids}; MRIQC: {mriqc}")
            return 0
        if args.command == "mriqc":
            return launch(args)
        if args.command == "build":
            state = build(
                args.bids, args.mriqc, args.output, args.config, args.extras, args.hash_images
            )
            print(f"Report: {args.output.resolve() / 'index.html'}")
        else:
            state = check(args.output, inputs=args.inputs)
            print(
                "Report integrity verified."
                + (" Live inputs verified." if args.inputs else " Live inputs not checked.")
            )
        print(json.dumps(state, indent=2))
        print("No exclusions made. Review flags and input completeness separately.")
        return 2 if args.strict and not state["core_inputs_complete"] else 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
