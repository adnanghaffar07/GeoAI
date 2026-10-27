"""Builds the Colab notebooks from the scripts, so the notebook needs no Google Drive upload.

The script is copied *into* the notebook. Never edit the notebook by hand: change the script,
then run `python notebooks/make_notebooks.py` from the `ml` folder. A test checks they match.
"""

from __future__ import annotations

import json
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent.parent
P8_1_NOTEBOOK = ML_DIR / "notebooks" / "p8_1_get_rdd2022.ipynb"
P8_1_SCRIPT = ML_DIR / "data_prep" / "fetch_rdd2022.py"
P8_2_NOTEBOOK = ML_DIR / "notebooks" / "p8_2_split_rdd2022.ipynb"
P8_2_SCRIPT = ML_DIR / "data_prep" / "split_rdd2022.py"
P8_4_NOTEBOOK = ML_DIR / "notebooks" / "p8_4_train.ipynb"
METRICS_SCRIPT = ML_DIR / "evaluation" / "metrics.py"
TRAIN_SCRIPT = ML_DIR / "training" / "train_frcnn.py"
P8_5_NOTEBOOK = ML_DIR / "notebooks" / "p8_5_final_test.ipynb"
EXAM_SCRIPT = ML_DIR / "evaluation" / "evaluate_test.py"
THRESHOLDS_FILE = ML_DIR / "config" / "acceptance-thresholds.yaml"
DRIVE_DIR = "/content/drive/MyDrive/GeoInfraLens"
RUN_DIR = f"{DRIVE_DIR}/runs/frcnn-rdd2022-0.1"


def _markdown(text: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _code(text: str) -> dict[str, object]:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.splitlines(keepends=True)}


def _requirements() -> str:
    lines = (ML_DIR / "requirements-data.txt").read_text().splitlines()
    return " ".join(f'"{line}"' for line in lines if line and not line.startswith("#"))


def _notebook(cells: list[dict[str, object]]) -> dict[str, object]:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
            "colab": {"provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


DRIVE_CELL = (
    "# {number}. Connect Google Drive and copy the cleaned dataset from it (about 3-5 minutes)\n"
    "import os, shutil, subprocess\n"
    "from google.colab import drive\n"
    "\n"
    "drive.mount('/content/drive')  # a sign-in popup may appear: choose your account and Allow\n"
    f"ZIP = '{DRIVE_DIR}/rdd2022-prepared-v1.zip'\n"
    "assert os.path.exists(ZIP), f'Not found: {{ZIP}}. It was saved at the end of P8.2.'\n"
    "if not os.path.exists('/content/prepared/split-manifest.json'):\n"
    "    shutil.copy(ZIP, '/content/data.zip')\n"
    "    subprocess.run(['unzip', '-q', '/content/data.zip', '-d', '/content'], check=True)\n"
    "    os.remove('/content/data.zip')\n"
    "print('Dataset ready:', sorted(os.listdir('/content/prepared')))\n"
)

HOW_TO_OPEN = (
    "**How to open this notebook:** go to colab.research.google.com → **File → Upload notebook** → choose this file "
    "from your computer (`ml/notebooks/{name}`). Nothing needs uploading to Google Drive.\n"
    "\n"
    "**How to run:** click ▶ on each grey cell from top to bottom and wait for the green tick before the next. "
    "No GPU is needed. Keep this tab open and your laptop awake.\n"
    "\n"
    "Only the public dataset is downloaded; nothing from your app or computer is sent here.\n"
)


def p8_1_notebook() -> dict[str, object]:
    cells = [
        _markdown(
            "# GeoInfraLens AI – P8.1: get the RDD2022 dataset\n"
            "\n"
            "Downloads the public **RDD2022** road-damage dataset (13.3 GB), checks it is the official, undamaged file, "
            "unpacks it **without the United States part** (Google Street View photos, not allowed for AI training), "
            "and counts what is inside.\n"
            "\n"
            "\n" + HOW_TO_OPEN.format(name="p8_1_get_rdd2022.ipynb") + "\n"
            "*Generated from `ml/data_prep/fetch_rdd2022.py` by `ml/notebooks/make_notebooks.py`. Do not edit by hand.*\n"
        ),
        # %%writefile must be the very first line of its cell.
        _code(f"%%writefile fetch_rdd2022.py\n# 1. Saves the download script (nothing runs yet)\n{P8_1_SCRIPT.read_text()}"),
        _code(
            f"# 2. Check free disk space (need about 30 GB) and install one small package\n!df -h /content | tail -1\n!pip install -q {_requirements()}\n"
        ),
        _code(
            "# 3. Download, check, unpack without the US part, and count (10-30 minutes)\n!python fetch_rdd2022.py --out /content/rdd2022\n"
        ),
        _code(
            "# 4. Download the counts file to your computer (your browser saves inventory.json)\n"
            "from google.colab import files\n"
            "\n"
            "files.download('/content/rdd2022/inventory.json')\n"
        ),
    ]
    return _notebook(cells)


def p8_2_notebook() -> dict[str, object]:
    cells = [
        _markdown(
            "# GeoInfraLens AI – P8.2: clean and split the dataset\n"
            "\n"
            "Downloads RDD2022 again (Colab forgets files when a session ends; about 10 minutes), then cleans it and splits it:\n"
            "- **test** = every labelled Czech photo (locked; never used for training),\n"
            "- **validation** = about 10% of each other country, **training** = the rest,\n"
            "- China drone photos and the United States part are left out,\n"
            "- duplicate and near-duplicate photos are handled so the test can't be cheated.\n"
            "\n" + HOW_TO_OPEN.format(name="p8_2_split_rdd2022.ipynb") + "\n"
            "Total time: about 40–60 minutes. At the end your browser downloads **`p8_2_results.zip`** (small: counts and lists, no photos).\n"
            "\n"
            "*Generated from `ml/data_prep/*.py` by `ml/notebooks/make_notebooks.py`. Do not edit by hand.*\n"
        ),
        _code(f"%%writefile fetch_rdd2022.py\n# 1. Saves the download script (nothing runs yet)\n{P8_1_SCRIPT.read_text()}"),
        _code(f"%%writefile split_rdd2022.py\n# 2. Saves the clean-and-split script (nothing runs yet)\n{P8_2_SCRIPT.read_text()}"),
        _code(
            f"# 3. Check free disk space (need about 40 GB) and install one small package\n!df -h /content | tail -1\n!pip install -q {_requirements()}\n"
        ),
        _code("# 4. Download, check and unpack without the US part (about 10 minutes)\n!python fetch_rdd2022.py --out /content/rdd2022\n"),
        _code(
            "# 5. Clean and split (about 20-40 minutes)\n!python split_rdd2022.py --data /content/rdd2022/data --out /content/rdd2022/prepared\n"
        ),
        _code(
            "# 6. Download the results to your computer (your browser saves p8_2_results.zip)\n"
            "!cd /content/rdd2022/prepared && zip -q -r /content/p8_2_results.zip split-manifest.json splits\n"
            "!du -sh /content/rdd2022/prepared\n"
            "from google.colab import files\n"
            "\n"
            "files.download('/content/p8_2_results.zip')\n"
        ),
    ]
    return _notebook(cells)


def p8_4_notebook() -> dict[str, object]:
    cells = [
        _markdown(
            "# GeoInfraLens AI – P8.4: train the baseline model\n"
            "\n"
            "Trains model **frcnn-rdd2022-0.1** on the cleaned dataset saved in your Google Drive in P8.2. "
            "Progress is saved to Drive about every 20 minutes, so little is lost if Colab disconnects. Training stops by itself with a clear message if Google Drive is nearly full (deleted files in Drive's Trash still use space).\n"
            "\n"
            "**Before you start: switch on the GPU.** Runtime → Change runtime type → **T4 GPU** → Save.\n"
            "\n"
            "**How to open this notebook:** colab.research.google.com → **File → Upload notebook** → choose "
            "`ml/notebooks/p8_4_train.ipynb` from your computer.\n"
            "\n"
            "**Training in sessions.** The whole training is 12 rounds (epochs). Each time you run this notebook it trains "
            "`EPOCHS_THIS_SESSION` rounds (set in cell 5; 2 rounds is roughly 1 hour), then stops cleanly and prints a short "
            "update. You can then close Colab and switch off your laptop. Next time, run all cells again: it continues with "
            "the next round. During a session keep this tab open and your laptop awake (free Colab stops when the tab closes).\n"
            "\n"
            "**If Colab disconnects in the middle of a session:** at most about 20 minutes of training is lost. "
            "Runtime → Disconnect and delete runtime, switch the GPU on again, upload this notebook again and run all cells.\n"
            "\n"
            "Only the public dataset is used; nothing from your app or computer is sent here.\n"
            "\n"
            "*Generated from `ml/evaluation/metrics.py` and `ml/training/train_frcnn.py` by "
            "`ml/notebooks/make_notebooks.py`. Do not edit by hand.*\n"
        ),
        _code(f"%%writefile metrics.py\n# 1. Saves the scoring rules (nothing runs yet)\n{METRICS_SCRIPT.read_text()}"),
        _code(f"%%writefile train_frcnn.py\n# 2. Saves the training script (nothing runs yet)\n{TRAIN_SCRIPT.read_text()}"),
        _code(
            "# 3. Check the GPU is switched on\n"
            "import torch, torchvision\n"
            "\n"
            "print('PyTorch', torch.__version__, '| torchvision', torchvision.__version__)\n"
            "assert torch.cuda.is_available(), 'No GPU: Runtime > Change runtime type > T4 GPU > Save, then run all cells again'\n"
            "print('GPU:', torch.cuda.get_device_name(0))\n"
        ),
        _code(DRIVE_CELL.format(number=4)),
        _code(
            "# 5. Train this session's rounds, then stop cleanly (continues from the last save)\n"
            "EPOCHS_THIS_SESSION = 2  # 2 rounds is roughly 1 hour; use 0 to train all remaining rounds in one go\n"
            "\n"
            "import os, subprocess\n"
            "\n"
            "command = ['python', 'train_frcnn.py', '--data', '/content/prepared',\n"
            f"           '--run-dir', '{RUN_DIR}', '--epochs-this-session', str(EPOCHS_THIS_SESSION)]\n"
            "process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,\n"
            "                           env={**os.environ, 'PYTHONUNBUFFERED': '1'})\n"
            "for line in process.stdout:  # show the training messages as they come\n"
            "    print(line, end='')\n"
            "exit_code = process.wait()\n"
            "\n"
            "# Make sure every save has reached Google Drive before Colab can stop\n"
            "drive.flush_and_unmount()\n"
            "if exit_code == 0:\n"
            "    print('All progress is stored in Google Drive. You can close Colab now.')\n"
            "else:\n"
            "    print('Training did NOT finish normally (see the STOPPED message above). Send that message to Claude.')\n"
        ),
        _code(
            "# 6. (Any time) How far has training got? Needs only cell 4 (Drive), not the GPU\n"
            "drive.mount('/content/drive')\n"
            f'!python train_frcnn.py --data /content/prepared --run-dir "{RUN_DIR}" --progress\n'
        ),
        _markdown(
            "### After each session\n"
            "Copy the update printed at the end of cell 5 (the small table) and send it to Claude. "
            "When all 12 rounds are done it prints *Training finished*. The trained model is "
            "`My Drive/GeoInfraLens/runs/frcnn-rdd2022-0.1/best.pt`; do not move or rename it.\n"
        ),
    ]
    return _notebook(cells)


def p8_5_notebook() -> dict[str, object]:
    cells = [
        _markdown(
            "# GeoInfraLens AI – P8.5: the final test (one time only)\n"
            "\n"
            "Gives the trained model **frcnn-rdd2022-0.1** its final exam on the **locked test photos** (all Czech, never "
            "seen in training), compares the result with the pass marks, and saves a plain-language report next to the "
            "model in Google Drive.\n"
            "\n"
            "**Only run this after training has finished** (P8.4 printed *Training finished*). The test photos may be used "
            "**once** per model, so the score is honest: a second run of the same model is refused.\n"
            "\n"
            "**Before you start: switch on the GPU.** Runtime → Change runtime type → **T4 GPU** → Save.\n"
            "\n"
            "**How to open this notebook:** colab.research.google.com → **File → Upload notebook** → choose "
            "`ml/notebooks/p8_5_final_test.ipynb` from your computer. Then **Runtime → Run all**. About 15–25 minutes.\n"
            "\n"
            "Only the public dataset is used; nothing from your app or computer is sent here.\n"
            "\n"
            "*Generated from `ml/evaluation/metrics.py`, `ml/evaluation/evaluate_test.py` and "
            "`ml/config/acceptance-thresholds.yaml` by `ml/notebooks/make_notebooks.py`. Do not edit by hand.*\n"
        ),
        _code(f"%%writefile metrics.py\n# 1. Saves the scoring rules (nothing runs yet)\n{METRICS_SCRIPT.read_text()}"),
        _code(f"%%writefile evaluate_test.py\n# 2. Saves the final-test script (nothing runs yet)\n{EXAM_SCRIPT.read_text()}"),
        _code(
            f"%%writefile acceptance-thresholds.yaml\n# 3. Saves the pass marks (frozen in P8.0; nothing runs yet)\n{THRESHOLDS_FILE.read_text()}"
        ),
        _code(
            "# 4. Check the GPU is switched on\n"
            "import torch, torchvision\n"
            "\n"
            "print('PyTorch', torch.__version__, '| torchvision', torchvision.__version__)\n"
            "assert torch.cuda.is_available(), 'No GPU: Runtime > Change runtime type > T4 GPU > Save, then run all cells again'\n"
            "print('GPU:', torch.cuda.get_device_name(0))\n"
        ),
        _code(DRIVE_CELL.format(number=5)),
        _code(
            "# 6. The final test (about 10-20 minutes). Prints the result and saves test-report.md next to the model\n"
            f'!python evaluate_test.py --data /content/prepared --model "{RUN_DIR}/best.pt" --thresholds acceptance-thresholds.yaml\n'
        ),
        _code(
            "# 7. Download the reports to your computer (your browser saves two small files)\n"
            "from google.colab import files\n"
            "\n"
            f"files.download('{RUN_DIR}/test-report.md')\n"
            f"files.download('{RUN_DIR}/test-report.json')\n"
        ),
        _markdown(
            "### After the test\n"
            "Send Claude the table printed at the end of cell 6, and put the two downloaded files in `ml/reports/`. "
            "Then **Runtime → Disconnect and delete runtime**. Do not run cell 6 again: the result is final for this model.\n"
        ),
    ]
    return _notebook(cells)


NOTEBOOKS = {P8_1_NOTEBOOK: p8_1_notebook, P8_2_NOTEBOOK: p8_2_notebook, P8_4_NOTEBOOK: p8_4_notebook, P8_5_NOTEBOOK: p8_5_notebook}


def main() -> None:
    for path, build in NOTEBOOKS.items():
        path.write_text(json.dumps(build(), indent=1) + "\n")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
