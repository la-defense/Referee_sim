"""应用参数记忆：JSON 配置文件（默认 %APPDATA%/RefereeSim/config.json）。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class AppSettings:
    mode: str = "串口"
    port: str = "COM4"
    baud: int = 115200
    scenario: int = 4
    robot_id: int = 7
    match_duration: float = 300.0
    shoot_interval: float = 0.6
    mqtt_host: str = "192.168.12.1"
    mqtt_port: int = 3333
    mqtt_client_id: str = "7"
    record_path: str = ""
    replay_path: str = ""
    replay_speed: float = 1.0
    window: tuple[int, int, int, int] = (100, 100, 1440, 900)


def settings_path() -> Path:
    override = os.environ.get("REFEREE_SIM_CONFIG")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "RefereeSim" / "config.json"


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or settings_path()
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppSettings()
    valid = {f.name for f in fields(AppSettings)}
    cleaned = {k: v for k, v in data.items() if k in valid}
    if "window" in cleaned and isinstance(cleaned["window"], list):
        cleaned["window"] = tuple(cleaned["window"])
    return AppSettings(**cleaned)


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(settings)
    data["window"] = list(data["window"])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
