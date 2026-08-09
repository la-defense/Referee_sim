import time

from referee_sim_app.client.messages import ALL_MESSAGES
from referee_sim_app.client.mqtt_client import MqttClient
from referee_sim_app.client.proto import decode_message, encode_message

from .mqtt_broker import MiniBroker


def _wait_until(predicate, timeout: float = 6.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_mqtt_publish_and_receive_roundtrip():
    broker = MiniBroker(port=0)
    broker.start()
    received: list[tuple[str, bytes, object]] = []
    client = MqttClient(
        host="127.0.0.1",
        port=broker.port,
        client_id="7",
        on_message=lambda topic, payload, schema: received.append((topic, payload, schema)),
    )
    try:
        client.connect()
        assert client.wait_connected(5.0)
        client.subscribe("GameStatus")
        assert _wait_until(lambda: len(broker.published) == 0)  # 等待订阅完成前的静默
        time.sleep(0.2)

        # 发送方向：CommonCommand 编码后发布，broker 记录 payload
        payload = client.publish("CommonCommand", {"cmd_type": 1, "param": 10})
        assert payload == b"\x08\x01\x10\x0a"
        assert _wait_until(lambda: any(t == "CommonCommand" for t, _ in broker.published))
        assert any(t == "CommonCommand" and p == b"\x08\x01\x10\x0a"
                   for t, p in broker.published)

        # 接收方向：同客户端发布 GameStatus，broker 回环投递给订阅者
        gs = ALL_MESSAGES["GameStatus"]
        raw = encode_message(gs, {"current_stage": 4, "stage_countdown_sec": -3})
        client.publish_raw("GameStatus", raw)
        assert _wait_until(lambda: any(t == "GameStatus" for t, _, _ in received))
        topic, data, schema = next(r for r in received if r[0] == "GameStatus")
        assert topic == "GameStatus"
        dec = decode_message(schema, data)
        assert dec["current_stage"] == 4
        assert dec["stage_countdown_sec"] == -3
    finally:
        client.disconnect()
        broker.stop()
