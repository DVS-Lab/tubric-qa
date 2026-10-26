# Configuration And Optional Metrics

Generate a complete starter configuration with `tubric-qa config`. Unknown keys
fail rather than being ignored. Supplying `metrics` replaces the full metric
dictionary, so edit the generated configuration when adding metrics.

## Plot Selection

Default plots contain smoothness (`fwhm_mean_mm`), tSNR (`tsnr`) and mean FD
(`fd_mean`), in that order. Only metrics configured and applicable to the image
type are plotted, so anatomy shows smoothness only. Supplementary MRIQC metrics
remain in the tables and review flags; hiding a panel does not change thresholds,
input-completeness checks, or exclusion decisions.

Set `plot_metrics` to a list of metric keys to choose panels, or to `null` to
plot every configured metric. Add optional metric keys here to display them.
Existing reports are unchanged. Reuse their saved tables for the simplified
layout without indexing or reading BIDS/MRIQC again:

```bash
tubric-qa replot /path/to/existing-report --output /path/to/new-simplified-report
tubric-qa check /path/to/new-simplified-report
```

The source report is verified first. All QC tables, thresholds, flags and
validation state are preserved, including unresolved input findings. Only
plots/presentation change. Original analysis provenance is retained alongside
new rendering provenance. This is a saved-snapshot refresh, not a new live-input
validation; add `--inputs` to `check` only when that additional check is wanted.

For studies that ran MRIQC for functional images only, add `--functional-only`
to `replot`. This creates a BOLD-only view from the same saved tables. It omits
anatomical rows and recalculates completeness counts for the selected scope,
without recalculating or changing any retained metrics, flags or thresholds.
Phase images remain explicitly not applicable. The original all-modality
report and its findings remain unchanged; this does not claim anatomical QC
was completed or constitute a fresh live-data inventory.

## Scanner Comparisons

The plotted scanner group combines Manufacturer, ManufacturersModelName and
the software label. Metadata inheritance is resolved by PyBIDS. These are
scanner descriptors, not a unique physical-scanner identifier. Serial numbers,
birthdates and acquisition dates are not copied into reports. For multi-site
studies, avoid interpreting this group as proof of the same physical scanner.

`software_labels` maps exact complete SoftwareVersions strings to display
labels. For example:

```json
{"software_labels": {"syngo MR XA60": "XA60", "syngo MR XA30": "XA30"}}
```

No label mapping changes threshold grouping by itself. By default software
groups are compared within the same threshold group. To also estimate fences
separately by scanner group, set:

```json
{"additional_group_fields": ["scanner_group"]}
```

This can greatly reduce group size. Always inspect `thresholds.tsv`. Allowed
additional fields: manufacturer, model, software_version, scanner_group.
The compulsory task/session/acquisition/echo/version grouping cannot be removed.

## Optional TEDANA, Coverage Or Other Numeric Metrics

First build a base MRIQC report and use the exact `image_id` in `run_qc.tsv`.
Do not join by subject alone or use heuristic filename matching. Add each new
metric to the configuration, including its units, applicable modalities and
review direction. Start as descriptive (`none`) until a policy is agreed:

```json
"tedana_rejected_fraction": {
  "label": "TEDANA rejected fraction", "unit": "fraction",
  "direction": "none", "modalities": ["bold"]
},
"brain_coverage_pct": {
  "label": "Reference-mask coverage", "unit": "%",
  "direction": "none", "modalities": ["bold"]
}
```

Example tab-delimited extras table (replace with actual IDs and values):

```tsv
image_id	metric_source	tedana_rejected_fraction	brain_coverage_pct
sub-example/func/sub-example_task-rest_bold.nii.gz	tedana-26.0.3; coverage-protocol-v1	0.25	98.0
```

```bash
tubric-qa build --bids /path/to/bids --mriqc /path/to/mriqc \
  --config study-qc.json --extras metrics.tsv --output /path/to/new-report
```

An extras row must have an exact, unique image_id and nonempty metric_source.
Unknown images/metrics, duplicate keys, nonnumeric values and attempts to
replace core MRIQC metrics are rejected. Absent optional measurements stay
missing. The entire extras file is fingerprinted for provenance.

You are responsible for documenting how external metrics were generated,
including code/version, masks/reference grid and units. The package does not
verify their scientific definition or their original imaging lineage. Never
mix different coverage denominators, masks/spaces, or TEDANA variants in a
single metric column. Use separately named metrics/configurations instead.
For multi-echo BIDS, do not replicate run-level TEDANA metrics across every
echo for statistical counting; use a documented representative image and
leave the other echo entries missing for that optional metric.

## Preserving Decisions

Keep approved scientific exclusions in your project's separate decision
ledger. TUBRIC QA reports all inventoried images and does not interpret or
modify that ledger. `review_flag_count` is not an exclusion column, and missing
values are not quality passes. Downstream analyses must join decisions
explicitly by the appropriate task/session/run, preserving usable other runs.
