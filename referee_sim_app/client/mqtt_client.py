"""MQTT 自定义客户端封装（paho-mqtt，QoS 1，topic 即指令名）。"""

from __future__ import annotations

import threading
from collections.abc import Callable

try:
    import paho.mqtt.client as mqtt
except ImportError:  # 允许未安装时导入其余模块
    mqtt = None

from .messages import topic_schema
from .proto import decode_message, encode_message


class MqttClient:
    def __init__(
        self,
        host: str = "192.168.12.1",
        port: int = 3333,
        client_id: str = "7",
        on_message: Callable[[str, bytes], None] | None = None,
        on_connect: Callable[[], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        if mqtt is None:
            raise RuntimeError("未安装 paho-mqtt")
        self.host = host
        self.port = port
        self.client_id = client_id
        self._on_message = on_message
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        self._client.on_connect = self._handle_connect
        self._client.on_message = self._handle_message
        self._client.on_disconnect = self._handle_disconnect
        self._connected = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def connect(self) -> None:
        self._connected.clear()
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()

    def disconnect(self) -> None:
        if mqtt is not None:
            try:
                self._client.disconnect()
            finally:
                self._client.loop_stop()
                self._connected.clear()

    def wait_connected(self, timeout: float = 5.0) -> bool:
        return self._connected.wait(timeout)

    def subscribe(self, topic: str) -> None:
        self._client.subscribe(topic, qos=1)

    def publish(self, topic: str, values: dict) -> bytes:
        """按 topic 对应的官方 schema 编码并发布，返回 payload。"""
        schema = topic_schema(topic)
        if schema is None:
            raise ValueError(f"未知 topic: {topic}")
        payload = encode_message(schema, values)
        self._client.publish(topic, payload, qos=1)
        return payload

    def publish_raw(self, topic: str, payload: bytes) -> None:
        self._client.publish(topic, payload, qos=1)

    def _handle_connect(self, _client, _userdata, _flags, reason_code, _properties=None) -> None:
        rc = getattr(reason_code, "value", reason_code)
        if rc == 0:
            self._connected.set()
            if self._on_connect:
                self._on_connect()

    def _handle_disconnect(self, *_args) -> None:
        self._connected.clear()
        if self._on_disconnect:
            self._on_disconnect()

    def _handle_message(self, _client, _userdata, msg) -> None:
        schema = topic_schema(msg.topic)
        if self._on_message:
            self._on_message(msg.topic, bytes(msg.payload), schema)
