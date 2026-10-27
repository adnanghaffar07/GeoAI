"""Tests for P8.1 fetch_rdd2022.py on a tiny fake dataset (the real one is 13 GB)."""

from __future__ import annotations

import hashlib
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from data_prep import fetch_rdd2022 as fetch


def voc(names: list[str], size: tuple[int, int] = (600, 600)) -> str:
    objects = "".join(
        f"<object><name>{name}</name><bndbox><xmin>1</xmin><ymin>1</ymin><xmax>9</xmax><ymax>9</ymax></bndbox></object>" for name in names
    )
    return f"<annotation><size><width>{size[0]}</width><height>{size[1]}</height></size>{objects}</annotation>"


def zip_bytes(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def fake_dataset(tmp_path: Path) -> Path:
    """Outer zip with one country as plain folders and two countries as inner zips (like RDD2022)."""
    norway = zip_bytes(
        {
            "Norway/train/images/n1.jpg": b"img",
            "Norway/train/annotations/xmls/n1.xml": voc(["D40", "D20"], (3650, 2044)),
            "Norway/test/images/n9.jpg": b"img",
        }
    )
    usa = zip_bytes(
        {
            "United_States/train/images/u1.jpg": b"img",
            "United_States/train/annotations/xmls/u1.xml": voc(["D40"]),
        }
    )
    outer = zip_bytes(
        {
            "RDD2022/Japan/train/images/j1.jpg": b"img",
            "RDD2022/Japan/train/images/j2.jpg": b"img",
            "RDD2022/Japan/train/annotations/xmls/j1.xml": voc(["D00", "D00", "D10"]),
            "RDD2022/Japan/train/annotations/xmls/j2.xml": voc([]),
            "RDD2022/RDD2022_Norway.zip": norway,
            "RDD2022/RDD2022_United_States.zip": usa,
            "RDD2022/United States/readme.txt": "also skipped",
        }
    )
    path = tmp_path / "rdd.zip"
    path.write_bytes(outer)
    return path


def test_extract_skips_united_states_everywhere(fake_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    report = fetch.Counter()
    fetch.extract(fake_dataset, out, report)

    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert not any("united" in name.lower() for name in written)
    assert "RDD2022/RDD2022_Norway/Norway/train/images/n1.jpg" in written  # inner zip unpacked in place
    assert report["skipped_excluded"] == 2  # the US inner zip and the US folder file
    assert report["inner_zips"] == 1  # the US zip is never even opened


def test_inventory_counts_per_country_and_label(fake_dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    fetch.extract(fake_dataset, out, fetch.Counter())
    inventory = fetch.build_inventory(out)["countries"]

    assert set(inventory) == {"Japan", "Norway"}
    assert inventory["Japan"]["images"] == {"train": 2}
    assert inventory["Japan"]["boxes_by_label"] == {"D00": 2, "D10": 1}
    assert inventory["Japan"]["images_without_boxes"] == 1
    assert inventory["Norway"]["images"] == {"train": 1, "test": 1}
    assert inventory["Norway"]["common_image_sizes"] == {"3650x2044": 1}


def test_inventory_refuses_excluded_data_on_disk(tmp_path: Path) -> None:
    stray = tmp_path / "data" / "United_States" / "train" / "images" / "u.jpg"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"img")
    with pytest.raises(fetch.DatasetError, match="Excluded data"):
        fetch.build_inventory(tmp_path / "data")


def test_broken_and_malicious_label_files_are_reported_not_trusted(tmp_path: Path) -> None:
    labels = tmp_path / "data" / "Czech" / "train" / "annotations" / "xmls"
    labels.mkdir(parents=True)
    (labels / "broken.xml").write_text("<annotation><object>")
    # "Billion laughs" style entity expansion: defusedxml must refuse it.
    (labels / "bomb.xml").write_text(
        '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "xxxxxxxx">]><annotation><object><name>&x;</name></object></annotation>'
    )
    result = fetch.build_inventory(tmp_path / "data")
    assert result["unreadable_label_file_count"] == 2
    assert result["countries"]["Czech"]["boxes_by_label"] == {}


@pytest.mark.parametrize("name", ["../evil.jpg", "/etc/passwd", "a/../../evil.jpg", "C:/evil.jpg", "..\\evil.jpg"])
def test_unsafe_paths_inside_the_zip_are_refused(tmp_path: Path, name: str) -> None:
    path = tmp_path / "bad.zip"
    path.write_bytes(zip_bytes({name: b"x"}))
    with pytest.raises(fetch.DatasetError, match="Unsafe path"):
        fetch.extract(path, tmp_path / "out", fetch.Counter())
    assert not (tmp_path / "evil.jpg").exists()


def test_md5_check(tmp_path: Path) -> None:
    file = tmp_path / "f.bin"
    file.write_bytes(b"hello")
    fetch.check_md5(file, hashlib.md5(b"hello").hexdigest())  # noqa: S324
    with pytest.raises(fetch.DatasetError, match="MD5 mismatch"):
        fetch.check_md5(file, "0" * 32)


class RangeServer(BaseHTTPRequestHandler):
    """Serves PAYLOAD and honours "Range: bytes=N-" like figshare's file host."""

    PAYLOAD = bytes(range(256)) * 400
    refuse_next = 0  # answer this many requests with refuse_code first (like figshare's limits)
    refuse_code = 403
    user_agents: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        RangeServer.user_agents.append(self.headers.get("User-Agent", ""))
        if RangeServer.refuse_next > 0:
            RangeServer.refuse_next -= 1
            self.send_error(RangeServer.refuse_code)
            return
        start = int(self.headers.get("Range", "bytes=0-").split("=")[1].rstrip("-") or 0)
        body = self.PAYLOAD[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server_url(monkeypatch: pytest.MonkeyPatch):
    RangeServer.refuse_next, RangeServer.refuse_code, RangeServer.user_agents = 0, 403, []
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)  # no real waiting in tests
    server = ThreadingHTTPServer(("127.0.0.1", 0), RangeServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/file"
    server.shutdown()


def test_download_resumes_a_partial_file(tmp_path: Path, server_url: str) -> None:
    payload = RangeServer.PAYLOAD
    dest = tmp_path / "dl.zip"
    dest.write_bytes(payload[:1000])  # as if the connection dropped
    fetch.download(server_url, dest, len(payload))
    assert dest.read_bytes() == payload
    fetch.download(server_url, dest, len(payload))  # already complete: nothing to do
    assert dest.read_bytes() == payload


def test_main_end_to_end_on_fake_data(fake_dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "run"
    out.mkdir()
    (out / fetch.DATASET_FILE).write_bytes(fake_dataset.read_bytes())
    monkeypatch.setattr(fetch, "DATASET_SIZE", fake_dataset.stat().st_size)
    monkeypatch.setattr(fetch, "DATASET_MD5", hashlib.md5(fake_dataset.read_bytes()).hexdigest())  # noqa: S324

    assert fetch.main(["--out", str(out)]) == 0
    inventory = json.loads((out / "inventory.json").read_text())
    assert set(inventory["countries"]) == {"Japan", "Norway"}
    assert inventory["unpack_report"]["skipped_excluded"] == 2
    assert not (out / fetch.DATASET_FILE).exists()  # zip removed to save disk


def test_main_stops_on_a_wrong_file(
    fake_dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "run"
    out.mkdir()
    (out / fetch.DATASET_FILE).write_bytes(fake_dataset.read_bytes())
    monkeypatch.setattr(fetch, "DATASET_SIZE", fake_dataset.stat().st_size)
    assert fetch.main(["--out", str(out)]) == 1  # real MD5 does not match the fake file
    assert "MD5 mismatch" in capsys.readouterr().err
    assert not (out / "data").exists()


def test_download_waits_and_retries_when_refused(tmp_path: Path, server_url: str) -> None:
    RangeServer.refuse_next = 2  # two "403 Forbidden" answers, then it works
    dest = tmp_path / "dl.zip"
    fetch.download(server_url, dest, len(RangeServer.PAYLOAD))
    assert dest.read_bytes() == RangeServer.PAYLOAD
    assert all(agent == fetch.USER_AGENT for agent in RangeServer.user_agents)  # identifies itself politely


def test_download_gives_up_with_clear_advice(tmp_path: Path, server_url: str) -> None:
    RangeServer.refuse_next = 99
    with pytest.raises(fetch.DatasetError, match="Gave up after 5 tries.*403.*Disconnect and delete runtime"):
        fetch.download(server_url, tmp_path / "dl.zip", len(RangeServer.PAYLOAD))


def test_download_does_not_retry_a_missing_file(tmp_path: Path, server_url: str) -> None:
    RangeServer.refuse_next, RangeServer.refuse_code = 99, 404
    with pytest.raises(fetch.DatasetError, match="404"):
        fetch.download(server_url, tmp_path / "dl.zip", len(RangeServer.PAYLOAD))
    assert len(RangeServer.user_agents) == 1
