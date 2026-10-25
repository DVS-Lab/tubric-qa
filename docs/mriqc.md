# Optional MRIQC Execution

MRIQC itself is a separate upstream tool. TUBRIC QA does not bundle its large
processing dependencies. Use your institution's approved pinned image/runtime.
Plan first; no processing occurs without `--execute`.

```bash
tubric-qa mriqc --bids /data/bids \
  --output /data/mriqc-new --work-dir /scratch/mriqc-new \
  --engine docker --image nipreps/mriqc:24.0.2 \
  --nprocs 8 --threads 1 --mem-gb 16
```

The tag above is an example, not a recommendation to change an existing study's
MRIQC version. Explicitly `docker pull` the chosen image first. Execution resolves
its installed image ID and runs that ID; the launch receipt records it. Tags
named `latest` and untagged images are rejected. Apptainer requires an existing
local SIF and records its SHA256; native execution records the executable hash
and `--version`, but is less isolated and does not fully freeze the dependency
environment.

Add `--existing /data/mriqc-old` to plan only participants with absent/invalid
MRIQC associations. Add `--execute` after inspecting the displayed command.
Both new output and work directories must not exist and must be separate from
BIDS and old results. Paths containing commas/colons/newlines are rejected for
container mounts. Arguments are passed as an argv array, not interpolated shell.

Docker mounts raw BIDS read-only and uses the current UID/GID. Apptainer uses
`--cleanenv --containall` with explicit input/output/work bindings. All engines
receive `--no-sub --notrack`, explicit processor/thread/memory settings and a
work directory. The user's umask is not changed.

The selection is subject/modality-level because MRIQC is the processing engine.
Within selected subjects, it may recompute images already represented in the
old root, but only in the fresh root. Existing results are never overwritten.
TUBRIC QA does not yet implement crash-resume or partial-output promotion for
MRIQC jobs. After a failure, preserve that output/log, inspect the cause and
use new output/work directories for a retry. Report generation can combine
multiple roots with explicit priority, keeping duplicate/ambiguous associations
visible instead of silently choosing or replacing measurements.

`tubric-qa-launch.json` records the actual command, runtime identity and exit
status; `tubric-qa-mriqc.log` captures processing output. Run a new `build` and
`check` afterward: MRIQC exit 0 is not proof that every expected image has an
IQM JSON. Valid IQM JSONs can also lack individual metrics, reported separately.

No MRIQC container was executed as part of this package's synthetic unit tests.
Before a large cohort, validate one representative participant on the target
platform, including multi-echo handling for your MRIQC version.
