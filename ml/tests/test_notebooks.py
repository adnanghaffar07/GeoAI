"""The Colab notebooks must contain exactly the current scripts (they are generated, never hand-edited)."""

import json

import pytest

from notebooks import make_notebooks


@pytest.mark.parametrize("path", list(make_notebooks.NOTEBOOKS))
def test_notebook_is_up_to_date(path) -> None:
    assert json.loads(path.read_text()) == make_notebooks.NOTEBOOKS[path](), "Run: python notebooks/make_notebooks.py"


@pytest.mark.parametrize(
    ("build", "scripts"),
    [
        (make_notebooks.p8_1_notebook, [make_notebooks.P8_1_SCRIPT]),
        (make_notebooks.p8_2_notebook, [make_notebooks.P8_1_SCRIPT, make_notebooks.P8_2_SCRIPT]),
        (make_notebooks.p8_4_notebook, [make_notebooks.METRICS_SCRIPT, make_notebooks.TRAIN_SCRIPT]),
        (make_notebooks.p8_5_notebook, [make_notebooks.METRICS_SCRIPT, make_notebooks.EXAM_SCRIPT, make_notebooks.THRESHOLDS_FILE]),
    ],
)
def test_notebook_embeds_its_scripts(build, scripts) -> None:
    cells = build()["cells"]
    for index, script in enumerate(scripts, start=1):
        source = "".join(cells[index]["source"])
        assert source.startswith(f"%%writefile {script.name}\n")
        assert script.read_text() in source
    everything = json.dumps(cells)
    if build in (make_notebooks.p8_1_notebook, make_notebooks.p8_2_notebook):  # later notebooks read the saved dataset from Drive
        assert "drive.mount" not in everything
        assert "defusedxml==0.7.1" in everything


def test_training_notebook_reads_the_saved_dataset_and_saves_runs_to_drive() -> None:
    everything = json.dumps(make_notebooks.p8_4_notebook()["cells"])
    assert "rdd2022-prepared-v1.zip" in everything
    assert "runs/frcnn-rdd2022-0.1" in everything
    assert "T4 GPU" in everything
    assert "'--epochs-this-session', str(EPOCHS_THIS_SESSION)" in everything and "--progress" in everything
    assert "if exit_code == 0" in everything  # "All progress is stored" only after a normal finish
    assert "test.json" not in everything


def test_final_test_notebook_uses_the_trained_model_and_the_frozen_pass_marks() -> None:
    everything = json.dumps(make_notebooks.p8_5_notebook()["cells"])
    assert "rdd2022-prepared-v1.zip" in everything
    assert "runs/frcnn-rdd2022-0.1/best.pt" in everything
    assert "--thresholds acceptance-thresholds.yaml" in everything
    assert "T4 GPU" in everything and "once" in everything
    assert "train_frcnn.py" not in everything.replace("`ml/training/train_frcnn.py`", "")  # never trains
