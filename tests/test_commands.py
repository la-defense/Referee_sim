import struct

import pytest

from referee_sim_app.protocol.commands import COMMANDS, decode_command, encode_command
from referee_sim_app.protocol.ui_graphics import Figure, build_figures_content, decode_interactive_content


def test_all_commands_have_expected_lengths():
    for cmd_id, spec in COMMANDS.items():
        data = encode_command(spec)
        assert len(data) == spec.length, (
            f"0x{cmd_id:04X}: 期望 {spec.length}B，实际 {len(data)}B"
        )


@pytest.mark.parametrize(
    "cmd_id,length",
    [(0x0001, 11), (0x0002, 1), (0x0003, 20), (0x0101, 4), (0x0104, 3), (0x0105, 3),
     (0x0201, 17), (0x0202, 14), (0x0203, 16), (0x0204, 8), (0x0206, 1), (0x0207, 7),
     (0x0208, 8), (0x0209, 5), (0x020A, 6), (0x020B, 40), (0x020C, 2), (0x020D, 14),
     (0x020E, 1), (0x0302, 30), (0x0303, 12), (0x0305, 48), (0x0306, 8), (0x0307, 105),
     (0x0308, 34), (0x0309, 30), (0x0310, 300), (0x0311, 30),
     (0x0A01, 24), (0x0A02, 12), (0x0A03, 10), (0x0A04, 8), (0x0A05, 41), (0x0A06, 6)])
def test_known_lengths(cmd_id, length):
    assert COMMANDS[cmd_id].length == length
    assert len(encode_command(COMMANDS[cmd_id])) == length


def test_game_state_bitfields():
    spec = COMMANDS[0x0001]
    data = encode_command(spec, {"game_type": 1, "game_progress": 4, "stage_remain_time": 300})
    assert data[0] == 0x41  # type=1 | progress(4)<<4
    assert struct.unpack_from("<H", data, 1)[0] == 300
    dec = decode_command(spec, data)
    assert dec["game_type"] == 1
    assert dec["game_progress"] == 4


def test_robot_status_official_length():
    spec = COMMANDS[0x0201]
    data = encode_command(spec, {
        "robot_id": 7, "robot_level": 1, "current_hp": 100, "maximum_hp": 100,
        "shooter_barrel_cooling_value": 0, "shooter_barrel_heat_limit": 240,
        "chassis_power_limit": 45, "bullet_speed_limit": 30.0,
        "gimbal_output": 1, "chassis_output": 1, "shooter_output": 1,
    })
    assert len(data) == 17
    assert struct.unpack_from("<f", data, 12)[0] == pytest.approx(30.0)
    assert data[16] == 0x07
    dec = decode_command(spec, data)
    assert dec["robot_id"] == 7 and dec["bullet_speed_limit"] == pytest.approx(30.0)


def test_mouse_bitgroups():
    spec = COMMANDS[0x0306]
    data = encode_command(spec, {"key_value": 0x1234, "x_position": 960, "mouse_left": 1,
                                 "y_position": 540, "mouse_right": 0})
    assert len(data) == 8
    dec = decode_command(spec, data)
    assert dec["x_position"] == 960
    assert dec["mouse_left"] == 1
    assert dec["y_position"] == 540


def test_interactive_content_figures():
    fig = Figure(b"abc", 1, 0, 7, 2, 3, 100, 200, 0, 0, 0, 300, 400)
    content = build_figures_content(0x0101, [fig])
    assert len(content) == 15
    back = decode_interactive_content(0x0101, content)["figures"][0]
    assert back.name == b"abc"
    assert back.operate == 1 and back.figure_type == 0
    assert back.layer == 7 and back.color == 2
    assert back.width == 3 and back.start_x == 100 and back.start_y == 200
    assert back.details_d == 300 and back.details_e == 400


def test_interactive_char_content():
    fig = Figure(b"c1", 1, 7, 8, 1, 2, 500, 600, 15, 5, 0, 0, 0)
    content = build_figures_content(0x0110, [fig], char_data="Power: 45.6".encode("utf-8"))
    assert len(content) == 45
    dec = decode_interactive_content(0x0110, content)
    assert dec["figure"].figure_type == 7
    assert dec["char_data"].rstrip(b"\x00") == b"Power: 45.6"


def test_interactive_sentry_and_radar():
    assert len(build_figures_content(0x0120, sentry_cmd=0x55)) == 4
    assert len(build_figures_content(0x0121, radar_cmd=b"\x01ABCDEF")) == 8


def test_0301_roundtrip():
    spec = COMMANDS[0x0301]
    content = build_figures_content(0x0101, [Figure(b"x", 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)])
    data = encode_command(spec, {"data_cmd_id": 0x0101, "sender_id": 7, "receiver_id": 0x0107},
                          content=content)
    assert len(data) == 6 + 15
    dec = decode_command(spec, data)
    assert dec["data_cmd_id"] == 0x0101
    assert dec["content"] == content
