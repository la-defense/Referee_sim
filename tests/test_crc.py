import struct

from referee_sim_app.protocol.crc import CRC16_TAB, CRC8_TAB, crc8, crc16


def test_crc8_table_matches_official_sample():
    # 官方附录/固件表：0x00,0x5e,0xbc,0xe2,0x61,...
    assert CRC8_TAB[:4] == [0x00, 0x5e, 0xbc, 0xe2]
    assert len(CRC8_TAB) == 256
    # 对一段头部数据计算 CRC8，与查表法逐字节等价
    data = bytes([0xA5, 0x0B, 0x00, 0x00])
    c = 0xFF
    for b in data:
        c = CRC8_TAB[(c ^ b) & 0xFF]
    assert crc8(data) == c


def test_crc16_table_matches_official_sample():
    assert CRC16_TAB[1] == 0x1189
    assert len(CRC16_TAB) == 256
    data = b"\xa5\x0b\x00\x00\xb8\x01\x00"
    c = 0xFFFF
    for b in data:
        c = ((c >> 8) ^ CRC16_TAB[((c ^ b) & 0xFF)]) & 0xFFFF
    assert crc16(data) == c


def test_crc16_bitwise_poly_8408_equivalent():
    # 反射多项式 0x8408 的逐位算法应与官方表一致
    def bitwise(data):
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                crc = ((crc >> 1) ^ 0x8408) & 0xFFFF if crc & 1 else (crc >> 1) & 0xFFFF
        return crc

    for n in (1, 7, 64, 300):
        data = bytes((i * 7 + n) & 0xFF for i in range(n))
        assert crc16(data) == bitwise(data)


def test_crc_append_properties():
    header = bytes([0xA5, 0x0B, 0x00, 0x00])
    crc = crc8(header)
    assert crc8(header + bytes([crc])) == 0x00  # 附加 CRC 后整体为 0
    body = bytes(range(10))
    tail = crc16(body)
    assert crc16(body + struct.pack("<H", tail)) == 0x0000
