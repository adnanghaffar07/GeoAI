"""Save-as-you-go for the long F2 steps: finished parts are remembered, a re-run continues where it stopped.

Each long step keeps its own work folder with progress.json. The "stamp" describes the inputs (data load, settings);
if it changes, that folder starts fresh, so old and new results are never mixed.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np


def stamp_of(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Checkpoints:
    def __init__(self, folder: Path, stamp: str, fresh: bool = False):
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.path = folder / "progress.json"
        state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        if fresh or state.get("stamp") != stamp:
            if state.get("done"):
                reason = "--restart was given" if fresh else "the inputs or settings changed"
                print(f"  {reason}: starting {folder.name} fresh", flush=True)
            for item in folder.rglob("*"):
                if item.is_file():
                    item.unlink()  # only files this step wrote itself
            state = {"stamp": stamp, "done": {}}
            self._write(state)
        elif state.get("done"):
            print(f"  continuing: {len(state['done'])} finished part(s) found in {folder.name}", flush=True)
        self.state = state

    def _write(self, state: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def done(self, name: str) -> bool:
        return name in self.state["done"]

    def info(self, name: str) -> Any:
        return self.state["done"].get(name)

    def mark(self, name: str, info: Any = True) -> None:
        self.state["done"][name] = info
        self._write(self.state)


def save_array(folder: Path, name: str, values: np.ndarray) -> None:
    """Write name.npy completely before it replaces an older one, so a crash never leaves half a file."""
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{name}.npy.tmp"
    with tmp.open("wb") as handle:
        np.save(handle, values)
    tmp.replace(folder / f"{name}.npy")


class Progress:
    """Prints 'label 120/490, 2.1 min so far, about 6 min left' at most every `every` seconds, and at the end."""

    def __init__(self, label: str, total: int, every: float = 20.0):
        self.label, self.total, self.every = label, max(total, 1), every
        self.count = 0
        self.start = self.last = time.monotonic()

    def step(self, amount: int = 1) -> None:
        self.count += amount
        now = time.monotonic()
        if now - self.last >= self.every or self.count >= self.total:
            self.last = now
            spent = (now - self.start) / 60
            left = spent / self.count * (self.total - self.count) if self.count else 0
            tail = "done" if self.count >= self.total else f"about {left:.1f} min left"
            print(f"  {self.label} {self.count:,}/{self.total:,}, {spent:.1f} min so far, {tail}", flush=True)
