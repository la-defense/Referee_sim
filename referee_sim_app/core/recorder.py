"""记录与回放：JSONL 格式（原始字节 + 时间戳）。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator


class Recorder:
    def __init__(self) -> None:
        self._fh = None
        self.path: Path | None = None

    def start(self, path: str | Path) -> None:
        self.stop()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8", newline="\n")

    def stop(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    @property
    def active(self) -> bool:
        return self._fh is not None

    def record(self, direction: str, data: bytes, meta: dict | None = None) -> None:
        if self._fh is None:
            return
        item = {"t": time.time(), "dir": direction, "hex": data.hex(), "meta": meta or {}}
        self._fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        self._fh.flush()


def iter_replay(path: str | Path, direction: str | None = None) -> Iterator[tuple[float, bytes, dict]]:
    """读取回放文件，产出 (相对延迟秒, 原始字节, meta)。"""
    items: list[tuple[float, bytes, dict]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if direction and item.get("dir") != direction:
                continue
            items.append((float(item["t"]), bytes.fromhex(item["hex"]), item.get("meta", {})))
    if not items:
        return
    t0 = items[0][0]
    for t, data, meta in items:
        yield max(0.0, t - t0), data, meta
