# Interpretation And Validation

## What Is Being Measured?

This package aggregates MRIQC's existing IQMs. It does not recalculate them
from raw NIfTI pixels. MRIQC performs its own processing for these metrics;
the resulting IQMs must not be described as final fMRIPrep/FEAT smoothness,
residual smoothness, or a direct readout of scanner reconstruction alone.

MRIQC functional FWHM fields are stored in voxel units. Each directional value
is multiplied by its corresponding MRIQC voxel spacing, and the three mm
values are averaged arithmetically. Do not multiply an average voxel FWHM by
an average spacing for anisotropic data. This measure is distinct from AFNI's
classic geometric-combined FWHM or ACF-effective FWHM.

MRIQC JSONs may contain flattened or nested metric dictionaries; both are
accepted. Missing spacing is not replaced with a guessed value. MRIQC version
is recorded and is part of threshold grouping. Changes in MRIQC definitions
or preprocessing can affect comparisons; users should inspect versions and
consult the corresponding MRIQC release/source before interpreting trends.

## One-Pass Review Flags

The lower/upper fences are Q1 - k*IQR and Q3 + k*IQR, with linear quartiles and
default k=1.5. Every metric uses all valid values in its applicable group in
one pass. There is no sequential removal, iterative clipping or data-driven
adjustment to maximize the sample. Flags from multiple metrics are retained
individually. They are never promoted to participant exclusion decisions.

Groups are modality, task, session, acquisition, direction, reconstruction,
echo, part and MRIQC version, with optional additional scanner grouping.
Separate run numbers within a group contribute separate measurements. Reported
image sample sizes therefore are not independent participant counts; repeated
run dependence and small cells preclude naive significance testing. Scanner
boxplots and upper-tail summaries are descriptive, not causal scanner effects.

Finite numeric values are required. Core nonnegative MRIQC metrics with
negative sentinel values are treated as missing. Booleans, NaN and infinity
are not accepted as numbers. Fewer than five values or zero IQR means not
classified. These choices are transparent in the threshold and flag tables.

## Validation Layers

1. Raw BIDS identity and basic NIfTI header readability/dimensions.
2. Exact MRIQC association, with missing/ambiguous/invalid/orphan records visible.
3. Metric availability and direction-specific review flags.
4. Output and input fingerprint verification through `check`.
5. Human inspection and project-specific scientific eligibility, outside this package.

Indexing with PyBIDS `validate=False` keeps parseable nonstandard target images
visible rather than silently discarding them. This is **not** a complete BIDS
validator. Only raw top-level sub-* folders and supported modalities are
included; derivatives, sourcedata, work and unsupported modalities are not
treated as raw acquisitions. Inspect a separate official BIDS validation
report. No behavioral-source, stimulus, timing or task-validity claims are made.

Only filenames are indexed in PyBIDS; its full metadata database is disabled.
Scanner fields (Manufacturer, ManufacturersModelName, SoftwareVersions) are
resolved from cached JSON sidecars at ancestor directories, with matching
suffix and entity values and no additional sidecar entities. Lower directories
override higher directories. Multiple applicable JSONs at the same directory
level are invalid under the BIDS inheritance rule and produce a metadata issue,
not a guessed software label. Malformed JSONs and identity conflicts also stay
visible. Inheritance is regression-tested against PyBIDS on valid inputs.
No metadata cache is reused between builds. All indexed raw JSONs remain
fingerprinted conservatively, including outside a task/session selection.

`check --inputs` verifies the recorded sources and discovers newly added images
and IQMs. Without `--hash-images`, same-size changes that preserve NIfTI mtimes
are not detectable. Output manifests are integrity checks, not signatures;
an attacker able to edit both a report and its manifest can alter both.

## Privacy

Only an explicit scanner metadata allowlist is copied from BIDS headers.
Header files are fingerprinted, not dumped. However IDs, paths, scanner strings,
optional metric-source text, reports and MRIQC logs can still be sensitive.
Review permissions before distributing. The report makes no external web
requests. MRIQC receives `--no-sub` and `--notrack`, but native/container
dependencies may need downloads for installation or templates. This package
does not promise a fully network-isolated MRIQC execution environment.

References: [MRIQC IQMs](https://mriqc.readthedocs.io/en/stable/iqms/bold.html),
[MRIQC running guide](https://mriqc.readthedocs.io/en/stable/running.html),
[PyBIDS](https://bids-standard.github.io/pybids/),
[BIDS specification](https://bids-specification.readthedocs.io/).
