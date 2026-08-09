"""应用核心：串口收发、调度、记录回放、错误注入。"""

from .injector import (
    concat_frames,
    corrupt_crc8,
    corrupt_crc16,
    flood_prefix,
    oversize_length,
    rebuild_seq,
    truncate_frame,
    zero_length,
)
from .scheduler import Scheduler, SchedEntry
from .transport import LoopbackTransport, SerialTransport, list_serial_ports

__all__ = [
    "Scheduler",
    "SchedEntry",
    "SerialTransport",
    "LoopbackTransport",
    "list_serial_ports",
    "corrupt_crc8",
    "corrupt_crc16",
    "oversize_length",
    "zero_length",
    "flood_prefix",
    "truncate_frame",
    "rebuild_seq",
    "concat_frames",
]
