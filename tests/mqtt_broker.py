"""最小 MQTT 3.1.1 broker（仅用于本地自动化验证，不支持鉴权/遗嘱/保留消息）。"""

from __future__ import annotations

import socket
import threading


def _encode_remaining(length: int) -> bytes:
    out = bytearray()
    while True:
        b = length % 128
        length //= 128
        if length:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


class MiniBroker:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._subs: dict[str, set] = {}
        self.published: list[tuple[str, bytes]] = []
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)

    def start(self) -> None:
        self._accept_thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                break
            t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            t.start()
            self._threads.append(t)

    @staticmethod
    def _read_exact(conn: socket.socket, n: int) -> bytes:
        chunks = []
        while n > 0:
            data = conn.recv(n)
            if not data:
                raise ConnectionError("连接关闭")
            chunks.append(data)
            n -= len(data)
        return b"".join(chunks)

    def _read_packet(self, conn: socket.socket) -> tuple[int, bytes]:
        first = self._read_exact(conn, 1)[0]
        remaining = 0
        multiplier = 1
        while True:
            b = self._read_exact(conn, 1)[0]
            remaining |= (b & 0x7F) * multiplier
            if not (b & 0x80):
                break
            multiplier *= 128
        return first, self._read_exact(conn, remaining)

    def _handle(self, conn: socket.socket) -> None:
        try:
            while True:
                first, payload = self._read_packet(conn)
                ptype = first >> 4
                if ptype == 1:  # CONNECT
                    conn.sendall(bytes([0x20, 0x02, 0x00, 0x00]))
                elif ptype == 3:  # PUBLISH
                    qos = (first >> 1) & 0x03
                    topic_len = int.from_bytes(payload[0:2], "big")
                    topic = payload[2:2 + topic_len].decode("utf-8", errors="replace")
                    pos = 2 + topic_len
                    packet_id = None
                    if qos > 0:
                        packet_id = payload[pos:pos + 2]
                        pos += 2
                    message = payload[pos:]
                    if qos == 1:
                        conn.sendall(bytes([0x40, 0x02]) + packet_id)
                    with self._lock:
                        self.published.append((topic, message))
                        targets = list(self._subs.get(topic, set()))
                    topic_bytes = topic.encode("utf-8")
                    rem = 2 + len(topic_bytes) + len(message)
                    for target in targets:
                        try:
                            target.sendall(bytes([0x30]) + _encode_remaining(rem)
                                           + len(topic_bytes).to_bytes(2, "big")
                                           + topic_bytes + message)
                        except OSError:
                            pass
                elif ptype == 8:  # SUBSCRIBE
                    packet_id = payload[0:2]
                    pos = 2
                    filters: list[str] = []
                    while pos < len(payload):
                        topic_len = int.from_bytes(payload[pos:pos + 2], "big")
                        pos += 2
                        topic = payload[pos:pos + topic_len].decode("utf-8", errors="replace")
                        pos += topic_len + 1  # 跳过 QoS 字节
                        filters.append(topic)
                    with self._lock:
                        for topic in filters:
                            self._subs.setdefault(topic, set()).add(conn)
                    conn.sendall(bytes([0x90, len(filters) + 2]) + packet_id
                                 + bytes(len(filters)))
                elif ptype == 12:  # PINGREQ
                    conn.sendall(bytes([0xD0, 0x00]))
                elif ptype == 14:  # DISCONNECT
                    break
        except (OSError, ConnectionError):
            pass
        finally:
            with self._lock:
                for topic in list(self._subs):
                    self._subs[topic].discard(conn)
            try:
                conn.close()
            except OSError:
                pass
