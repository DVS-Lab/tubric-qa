# TUBRIC QA

**Portable, review-first QC reports for BIDS datasets and MRIQC.**

Generate the cohort histograms, scanner/software comparisons and image-level
tables used in our RF1 work without requiring RF1 directory conventions,
fMRIPrep, TEDANA, a particular scanner, or specific task names. Runs, sessions,
acquisitions and echoes are kept distinct. The package never excludes a
participant or changes an image.

![Synthetic scanner-comparison preview](docs/images/synthetic-preview.png)

*The preview is fabricated demo data, not participant data or scientific results.*

## Quick Start

Use Python 3.13 for the pinned reference environment (the package supports
Python 3.10+ with independently resolved dependencies). Linux/macOS are the
supported command-line platforms. MRIQC execution additionally requires its
native installation, Docker, or Apptainer; report generation does not.

```bash
git clone https://github.com/DVS-Lab/tubric-qa.git
cd tubric-qa
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-build-isolation --no-deps -e .

tubric-qa build \
  --bids /path/to/bids \
  --mriqc /path/to/mriqc \
  --output /path/to/qc-report
tubric-qa check /path/to/qc-report --inputs
```

Open `/path/to/qc-report/index.html` in a browser. It is a self-contained folder
of local HTML, PNGs and tables; no server, login, telemetry, external JavaScript
or internet connection is needed to view it. Share the folder, not only HTML.
**Review its identifiers and local paths before sharing. It is not anonymized.**

Alternatively, `python -m pip install .` resolves compatible dependencies;
record the resulting environment and commit for your study.

## What You Get

| Output | Purpose |
|---|---|
| `index.html`, `figures/*.png` | Offline cohort report, histograms and scanner/software boxplots |
| `run_qc.tsv` | One row per raw BOLD/T1w/T2w image, matching status and metric values |
| `flags.tsv` | Per-image, per-metric review flags with explicit missing/unevaluated states |
| `thresholds.tsv` | Group sizes, quartiles and review fences |
| `scanner_summary.tsv` | Scanner-group medians, quartiles, upper tails and missingness |
| `orphan_mriqc.tsv` | MRIQC JSONs with no exact raw-image match |
| `config.json`, `methods.md` | Exact rules and methodological description |
| `provenance.json`, `validation.json` | Versions, code/input/output fingerprints and completeness |

Default functional metrics: **tSNR, mean FD, standardized DVARS, MRIQC FWHM,
EFC and FBER**. Structural T1w/T2w reports include FWHM, EFC, FBER, CNR and CJV.
TEDANA, brain coverage and other metrics can be added through an explicit,
exact-image-keyed table and metric configuration; they are not required.

## Rules That Prevent Silent Cohort Loss

- Flags are **not exclusion decisions**. No selected-subject list is generated.
- Fences use linear quartiles and 1.5 IQR, in a **single parallel pass**. A flag
  for one metric does not remove a row before another metric is evaluated.
- Thresholds never cross task/session, acquisition, direction, reconstruction,
  echo, part, modality or MRIQC-version boundaries. Optional scanner grouping
  is explicit. Runs are not pooled across sessions, nor collapsed per subject.
- Fewer than five values or zero IQR means **not classified**, not a pass.
- Smoothness is descriptive by default, not a "high is bad" rule.
- Missing/invalid metrics remain `n/a`, not zero or FALSE. Ambiguous source
  matches stop metric association instead of selecting an arbitrary file.
- All echoes are inventoried separately. If MRIQC only processed one echo,
  others are reported missing. They are not assigned that echo's IQMs.
- Source images are read only. Output directories must be new and separate
  from inputs; there is no overwrite flag. Your shell's umask is honored.

These defaults are starting points for review, not universal clinical or
scientific acceptance thresholds. Small, heterogeneous groups and repeated
runs require care. See [methods and interpretation](docs/methods.md).

## Try It Without Study Data

```bash
tubric-qa demo demo-data
tubric-qa build --bids demo-data/bids --mriqc demo-data/mriqc --output reports/demo
tubric-qa check reports/demo --inputs
```

The deterministic demo contains two tasks, two sessions, two fictional software
versions, an extreme motion value and one deliberately missing MRIQC JSON.
The latter is supposed to be reported. `--strict` returns exit 2 for that
incompleteness while still producing the report.

## MRIQC Missing?

Use the optional launcher to inspect a plan first. Nothing runs without
`--execute`. Choose an MRIQC version appropriate for your study and explicitly
pull its pinned image or provide a local SIF. Resource limits are required
by defaults, not inferred from the full machine's core count.

```bash
tubric-qa mriqc --bids /path/to/bids \
  --existing /path/to/existing-mriqc \
  --output /path/to/new-mriqc --work-dir /scratch/new-mriqc-work \
  --engine apptainer --image /containers/mriqc-version.sif \
  --nprocs 8 --threads 1 --mem-gb 16
# Review the plan; repeat the same command with --execute to run it.
```

Omit `--existing` when no MRIQC output exists. The launcher selects subjects
with missing/invalid associations and writes a **fresh output**, preserving all
existing MRIQC results. MRIQC runs the requested modalities for those subjects,
so some existing scans may be measured again in the new directory. It does not
claim per-image resume. To retain original measurements and fill gaps:

```bash
tubric-qa build --bids /path/to/bids \
  --mriqc /path/to/existing-mriqc --mriqc /path/to/new-mriqc \
  --output /path/to/new-qc-report
```

The first root with an exact match takes precedence, and shadowed candidate
counts are recorded. Duplicates *within* a root remain ambiguous. An invalid
primary match is not silently replaced: explicitly fix or change root priority.
MRIQC receives `--no-sub --notrack`. See [MRIQC execution](docs/mriqc.md).

## Configuration And Optional Metrics

```bash
tubric-qa config > study-qc.json
# Edit this generated configuration, then:
tubric-qa build --bids /path/to/bids --mriqc /path/to/mriqc \
  --config study-qc.json --output /path/to/configured-report
```

Software labels use full inherited BIDS `SoftwareVersions` values by default.
The `software_labels` mapping allows explicit exact-string aliases such as a
study's scanner eras. No dates or vendor-specific codes are guessed. Consult
[configuration and optional metrics](docs/configuration.md) for TEDANA and
coverage examples.

## Reproducibility And Limitations

`check` verifies every report artifact against its manifest; `check --inputs`
also verifies source fingerprints and detects newly added BIDS/MRIQC files.
Metadata and IQMs receive full SHA256 hashes. Images use size/mtime by default
to avoid reading entire cohorts; add `build --hash-images` for full hashes.
These are integrity checks, not a cryptographic signature or scientific approval.

Currently supports **BOLD, T1w and T2w**. It does not run preprocessing, smooth
images, infer event validity, calculate template coverage without supplied
metrics, diagnose registration failures, or support diffusion/PET/EEG QC.
PyBIDS indexing is not a full BIDS validation. Run the official BIDS validator
and inspect MRIQC's individual visual reports as well. A numeric cohort plot
cannot substitute for those checks.

Exit codes: **0** report/check completed, **1** operational or integrity error,
**2** core input incompleteness with `--strict`. QC outlier flags alone never
cause a failure exit. MRIQC execution returns MRIQC's process status.

## Development

```bash
python -m pytest -q
python -m ruff check src tests
python -m build --no-isolation
```

Tests use synthetic data and mocked MRIQC launchers; no participant data are
included. The local test suite does not establish end-to-end MRIQC container
performance on every platform. CI runs the package tests and builds artifacts.

MIT licensed. Developed by the Temple University Neuroeconomics Lab, with
design lessons from `rf1-sra-linux2`. No RF1 participant data, paths, eligibility
rules or task-specific mappings are bundled. Please cite
[MRIQC](https://doi.org/10.1371/journal.pone.0184661) and the tools that produced
your metrics, and report the TUBRIC QA commit/configuration used.
