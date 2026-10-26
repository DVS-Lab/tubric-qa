import json
from copy import deepcopy

import pytest

from tubric_qa.config import load_config
from tubric_qa.report import figures, plotted_metrics
from tubric_qa.statistics import calculate
from test_statistics import records


def test_default_panels_and_anatomy():
    config = load_config()
    assert plotted_metrics(config, "bold") == ["fwhm_mean_mm", "tsnr", "fd_mean"]
    assert plotted_metrics(config, "T1w") == ["fwhm_mean_mm"]
    config["metrics"] = {"fd_mean": config["metrics"]["fd_mean"]}
    assert plotted_metrics(config, "bold") == ["fd_mean"]


def test_all_panels_and_legacy_configuration():
    config = load_config()
    config["plot_metrics"] = None
    assert "dvars_std" in plotted_metrics(config, "bold")
    del config["plot_metrics"]
    assert "dvars_std" in plotted_metrics(config, "bold")


@pytest.mark.parametrize("selection", [[], "tsnr", ["unknown"], ["tsnr", "tsnr"], [{}]])
def test_invalid_plot_selection(tmp_path, selection):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"plot_metrics": selection}))
    with pytest.raises(ValueError, match="plot_metrics"):
        load_config(path)


def test_plot_selection_leaves_flags_and_thresholds_unchanged():
    rows = records([0.1, 0.2, 0.3, 0.4, 8])
    config = load_config()
    simplified = calculate(deepcopy(rows), config)
    config["plot_metrics"] = None
    assert calculate(deepcopy(rows), config) == simplified


def test_default_renders_one_three_metric_figure(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    config = load_config()
    rows = records([0.1, 0.2, 0.3, 0.4, 8])
    thresholds, _, _ = calculate(rows, config)
    real_subplots = plt.subplots
    dimensions = []

    def capture(*args, **kwargs):
        dimensions.append(args)
        return real_subplots(*args, **kwargs)

    monkeypatch.setattr(plt, "subplots", capture)
    links = figures(tmp_path, rows, config, thresholds)
    assert len(links) == 1
    assert dimensions == [(3, 2)]
    assert (tmp_path / links[0][1]).is_file()
