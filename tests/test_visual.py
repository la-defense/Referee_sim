import pytest

from referee_sim_app.core.visual import (
    path_points_from_0307,
    robot_positions_from_0305,
    utf16_text,
)


def test_robot_positions_from_0305():
    values = {
        "opponent_hero_x": 100, "opponent_hero_y": 200,
        "opponent_sentry_x": 0, "opponent_sentry_y": 0,  # 未发送，跳过
        "ally_std3_x": 300, "ally_std3_y": 400,
    }
    positions = robot_positions_from_0305(values)
    assert positions == [
        {"label": "敌方英雄", "x_m": 1.0, "y_m": 2.0, "side": "enemy"},
        {"label": "己方步兵3", "x_m": 3.0, "y_m": 4.0, "side": "ally"},
    ]


def test_path_points_from_0307():
    values = {
        "start_position_x": 100,  # dm → 10.0 m
        "start_position_y": 200,  # dm → 20.0 m
        "delta_x": bytes([1, 0xFF, 2]),  # 0xFF → -1
        "delta_y": bytes([0, 1, 0xFE]),  # 0xFE → -2
    }
    points = path_points_from_0307(values)
    expected = [(10.0, 20.0), (10.1, 20.0), (10.0, 20.1), (10.2, 19.9)]
    assert len(points) == len(expected)
    for got, want in zip(points, expected):
        assert got[0] == pytest.approx(want[0])
        assert got[1] == pytest.approx(want[1])


def test_utf16_text():
    data = "功率:45W".encode("utf-16-le") + b"\x00\x00\x00\x00"
    assert utf16_text(data) == "功率:45W"
    assert utf16_text(b"") == ""
