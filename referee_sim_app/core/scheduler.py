"""周期发送调度器（官方频率）。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class SchedEntry:
    cmd_id: int
    interval: float
    builder: Callable[[], bytes]
    enabled: bool = True
    next_time: float = 0.0


class Scheduler:
    """按单调时钟调度周期任务；tick 返回所有到期帧。"""

    def __init__(self) -> None:
        self.entries: dict[int, SchedEntry] = {}
        self._start = time.monotonic()

    def add(self, entry: SchedEntry) -> None:
        entry.next_time = self._start
        self.entries[entry.cmd_id] = entry

    def remove(self, cmd_id: int) -> None:
        self.entries.pop(cmd_id, None)

    def clear(self) -> None:
        self.entries.clear()

    def tick(self, now: float | None = None) -> list[bytes]:
        now = time.monotonic() if now is None else now
        due: list[bytes] = []
        for entry in self.entries.values():
            if not entry.enabled or entry.interval <= 0:
                continue
            if now >= entry.next_time:
                due.append(entry.builder())
                entry.next_time += entry.interval
                while entry.next_time <= now:
                    entry.next_time += entry.interval
        return due
