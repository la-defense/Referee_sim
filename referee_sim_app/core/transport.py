"""串口传输抽象：真实串口 / 回环（无需硬件）。"""

from __future__ import annotations

import threading
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # 允许在未安装 pyserial 时导入其余模块
    serial = None


def list_serial_ports() -> list[str]:
    if serial is None:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


class Transport(ABC):
    def __init__(self, rx_callback: Callable[[bytes], None] | None = None) -> None:
        self._rx_callback = rx_callback

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def write(self, data: bytes) -> None: ...

    @abstractmethod
    def is_open(self) -> bool: ...


class SerialTransport(Transport):
    """pyserial 真实串口；读取在后台线程，数据通过回调上抛。"""

    def __init__(self, port: str, baud: int, rx_callback: Callable[[bytes], None] | None = None) -> None:
        super().__init__(rx_callback)
        if serial is None:
            raise RuntimeError("未安装 pyserial")
        self.port = port
        self.baud = baud
        self._ser: serial.Serial | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def open(self) -> None:
        if self._ser is not None:
            return
        self._ser = serial.Serial(self.port, self.baud, timeout=0.05)
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, name="referee-sim-rx", daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        assert self._ser is not None
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(256)
            except Exception:
                break
            if chunk and self._rx_callback:
                try:
                    self._rx_callback(bytes(chunk))
                except Exception as exc:  # 回调异常不应杀死读线程
                    print(f"[referee-sim] rx callback error: {exc}", file=sys.stderr)

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise RuntimeError("串口未打开")
        self._ser.write(data)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open


class LoopbackTransport(Transport):
    """回环模式：发送的字节直接进入本地接收回调，用于无硬件自测。"""

    def __init__(self, rx_callback: Callable[[bytes], None] | None = None) -> None:
        super().__init__(rx_callback)
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> None:
        if not self._open:
            raise RuntimeError("回环未打开")
        if self._rx_callback:
            self._rx_callback(data)

    def is_open(self) -> bool:
        return self._open
