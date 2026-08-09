import struct

import pytest

from referee_sim_app.protocol.crc import crc8, crc16
from referee_sim_app.protocol.frame import FrameParser, build_frame
from referee_sim_app.core.injector import (
    concat_frames,
    corrupt_crc8,
    corrupt_crc16,
    flood_prefix,
    oversize_length,
    rebuild_seq,
    truncate_frame,
    zero_length,
)


def test_build_frame_structure():
    fr = build_frame(0x0001, bytes(11), seq=7)
    assert fr[0] == 0xA5
    assert struct.unpack_from("<H", fr, 1)[0] == 11
    assert fr[3] == 7
    assert crc8(fr[:4]) == fr[4]
    assert crc16(fr[: -2]) == struct.unpack("<H", fr[-2:])[0]
    assert len(fr) == 5 + 2 + 11 + 2


def test_parser_single_and_multi_frame():
    p = FrameParser()
    fr1 = build_frame(0x0001, bytes(11), seq=1)
    fr2 = build_frame(0x0201, bytes(17), seq=2)
    frames = p.feed(fr1 + fr2)
    assert [f.cmd_id for f in frames] == [0x0001, 0x0201]
    assert [f.seq for f in frames] == [1, 2]
    assert frames[0].data == bytes(11)


def test_parser_partial_frame():
    p = FrameParser()
    fr = build_frame(0x0001, bytes(11), seq=3)
    assert p.feed(fr[:8]) == []
    assert p.pending == fr[:8]
    out = p.feed(fr[8:])
    assert len(out) == 1 and out[0].cmd_id == 0x0001
    assert p.pending == b""


def test_parser_rejects_bad_crc8_and_crc16():
    fr = build_frame(0x0001, bytes(11), seq=0)
    p1 = FrameParser()
    assert p1.feed(corrupt_crc8(fr)) == []
    assert p1.pending == fr[-4:]  # 滑过坏字节后残留不足 5 字节的数据
    p2 = FrameParser()
    assert p2.feed(corrupt_crc16(fr)) == []
    assert len(p2.pending) == 4


def test_parser_oversize_and_flood():
    fr = build_frame(0x0001, bytes(11), seq=0)
    p = FrameParser()
    # 超大长度：声明 0xFFFF 但只发出 9 字节
    assert p.feed(oversize_length(fr)) == []
    assert len(p.pending) == 4
    p2 = FrameParser()
    out = p2.feed(flood_prefix(fr))
    assert [f.raw for f in out] == [fr] and p2.pending == b""


def test_parser_zero_length_keeps_frame():
    fr = build_frame(0x0001, bytes(11), seq=0)
    p = FrameParser()
    out = p.feed(zero_length(fr))
    assert len(out) == 1 and out[0].cmd_id == 0x0001 and out[0].data == b""


def test_truncated_and_seq():
    fr = build_frame(0x0001, bytes(11), seq=0)
    p = FrameParser()
    assert p.feed(truncate_frame(fr)) == []
    assert p.pending != b""
    out = FrameParser().feed(rebuild_seq(fr, 42))
    assert out[0].seq == 42


def test_concat_parsed_in_one_feed():
    frames = [build_frame(c, bytes(n), seq=i) for i, (c, n) in
              enumerate([(0x0001, 11), (0x0201, 17), (0x0202, 14)])]
    out = FrameParser().feed(concat_frames(*frames))
    assert [f.cmd_id for f in out] == [0x0001, 0x0201, 0x0202]
