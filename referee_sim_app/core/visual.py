"""上行数据 → 可视化模型的转换（纯逻辑，可测试）。"""

from __future__ import annotations


FIELD_W = 28.0  # m
FIELD_H = 15.0  # m


def robot_positions_from_0305(values: dict) -> list[dict]:
    """0x0305 小地图接收雷达数据 → 机器人位置列表。

    坐标单位为 cm；x/y 为 0 表示该机器人未发送坐标。
    返回 [{label, x_m, y_m, side}]，side: 'enemy' | 'ally'。
    """
    pairs = [
        ("敌方英雄", "opponent_hero_x", "opponent_hero_y", "enemy"),
        ("敌方工程", "opponent_engineer_x", "opponent_engineer_y", "enemy"),
        ("敌方步兵3", "opponent_std3_x", "opponent_std3_y", "enemy"),
        ("敌方步兵4", "opponent_std4_x", "opponent_std4_y", "enemy"),
        ("敌方空中", "opponent_aerial_x", "opponent_aerial_y", "enemy"),
        ("敌方哨兵", "opponent_sentry_x", "opponent_sentry_y", "enemy"),
        ("己方英雄", "ally_hero_x", "ally_hero_y", "ally"),
        ("己方工程", "ally_engineer_x", "ally_engineer_y", "ally"),
        ("己方步兵3", "ally_std3_x", "ally_std3_y", "ally"),
        ("己方步兵4", "ally_std4_x", "ally_std4_y", "ally"),
        ("己方空中", "ally_aerial_x", "ally_aerial_y", "ally"),
        ("己方哨兵", "ally_sentry_x", "ally_sentry_y", "ally"),
    ]
    result = []
    for label, xk, yk, side in pairs:
        x = values.get(xk, 0) or 0
        y = values.get(yk, 0) or 0
        if x == 0 and y == 0:
            continue
        result.append({"label": label, "x_m": x / 100.0, "y_m": y / 100.0, "side": side})
    return result


def path_points_from_0307(values: dict) -> list[tuple[float, float]]:
    """0x0307 路径数据 → 路径点列表（米）。

    起点单位为 dm，49 个增量（int8，dm）。
    """
    sx = float(values.get("start_position_x", 0) or 0) / 10.0
    sy = float(values.get("start_position_y", 0) or 0) / 10.0
    dx = values.get("delta_x", b"") or b""
    dy = values.get("delta_y", b"") or b""
    points = [(sx, sy)]
    cx, cy = sx, sy
    for i in range(min(len(dx), len(dy), 49)):
        cx += (dx[i] if dx[i] < 128 else dx[i] - 256) / 10.0
        cy += (dy[i] if dy[i] < 128 else dy[i] - 256) / 10.0
        points.append((cx, cy))
    return points


def utf16_text(data: bytes) -> str:
    """0x0308 自定义消息按 UTF-16LE 解码（去除结尾 NUL）。"""
    if not data:
        return ""
    try:
        text = data.decode("utf-16-le", errors="replace")
    except Exception:
        text = data.decode("utf-8", errors="replace")
    return text.rstrip("\x00").rstrip("\ufffd")
