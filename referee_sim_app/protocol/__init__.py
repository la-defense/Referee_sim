"""协议核心：CRC、帧格式、命令定义、UI 图形解析。"""

from .crc import crc8, crc16
from .frame import FrameParser, ParsedFrame, build_frame
from .commands import COMMANDS, CommandSpec, decode_command, encode_command

from . import frame as _frame
_frame.register_names({cmd.cmd_id: cmd.name for cmd in COMMANDS.values()})

__all__ = [
    "COMMANDS",
    "CommandSpec",
    "FrameParser",
    "ParsedFrame",
    "build_frame",
    "crc8",
    "crc16",
    "decode_command",
    "encode_command",
]
