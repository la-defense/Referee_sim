import struct

from referee_sim_app.protocol.frame import FrameParser, build_frame
from referee_sim_app.protocol.ui_graphics import (
    COLORS,
    FIGURE_TYPES,
    Figure,
    build_figures_content,
    decode_figure,
    decode_interactive_content,
)


def test_figure_bitfield_roundtrip_all_types():
    for ftype in FIGURE_TYPES:
        fig = Figure(b"t1", 1, ftype, 9, 8, 511, 1023, 1024, 300, 400, 500, 700, 900)
        raw = fig.to_bytes()
        assert len(raw) == 15
        back = decode_figure(raw)
        for attr in ("name", "operate", "figure_type", "layer", "color", "width",
                     "start_x", "start_y", "details_a", "details_b", "details_c",
                     "details_d", "details_e"):
            expected = fig.name.ljust(3, b"\x00") if attr == "name" else getattr(fig, attr)
            assert getattr(back, attr) == expected, attr


def test_figure_config_bit_layout():
    # 手拼 15 字节验证位域布局（与官方表 1-27 一致）
    fig = Figure(b"abc", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    raw = fig.to_bytes()
    cfg1, cfg2, cfg3 = struct.unpack_from("<III", raw, 3)
    assert cfg1 & 0x7 == 1
    assert (cfg1 >> 3) & 0x7 == 2
    assert (cfg1 >> 6) & 0xF == 3
    assert (cfg1 >> 10) & 0xF == 4
    assert (cfg1 >> 14) & 0x1FF == 8
    assert (cfg1 >> 23) & 0x1FF == 9
    assert cfg2 & 0x3FF == 5
    assert (cfg2 >> 10) & 0x7FF == 6
    assert (cfg2 >> 21) & 0x7FF == 7
    assert cfg3 & 0x3FF == 10
    assert (cfg3 >> 10) & 0x7FF == 11
    assert (cfg3 >> 21) & 0x7FF == 12


def test_int_float_value():
    # details_c/d/e = 1,2,3 -> 1 | 2<<10 | 3<<21
    fig = Figure(b"x", 1, 5, 0, 0, 1, 0, 0, 15, 0, 1, 2, 3)
    assert fig.int_value == (1 | (2 << 10) | (3 << 21))
    assert fig.float_value == fig.int_value / 1000.0


def test_frame_with_ui_content_parses():
    fig = Figure(b"ss0", 1, 7, 8, 2, 2, 150, 750, 15, 6, 0, 0, 0)
    content = build_figures_content(0x0110, [fig], char_data="chassis:")
    frame = build_frame(0x0301, b"\x10\x01\x07\x00\x07\x01" + content, seq=1)
    parsed = FrameParser().feed(frame)[0]
    assert parsed.cmd_id == 0x0301
    header = parsed.data[:6]
    assert struct.unpack_from("<H", header, 0)[0] == 0x0110
    dec = decode_interactive_content(0x0110, parsed.data[6:])
    assert dec["figure"].name_str == "ss0"
    assert dec["char_data"].rstrip(b"\x00") == b"chassis:"


def test_color_map():
    assert COLORS[8] == "白色"
