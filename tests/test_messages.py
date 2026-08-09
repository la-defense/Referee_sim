import math

from referee_sim_app.client.messages import ALL_MESSAGES, MESSAGE_TOPICS
from referee_sim_app.client.proto import decode_message, encode_message


def test_topic_count():
    assert len(ALL_MESSAGES) == 36
    assert len(MESSAGE_TOPICS) == 36


def test_known_message_encodings():
    kb = ALL_MESSAGES["KeyboardMouseControl"]
    assert encode_message(kb, {"mouse_x": 1}) == b"\x08\x01"
    cc = ALL_MESSAGES["CommonCommand"]
    assert encode_message(cc, {"cmd_type": 1, "param": 10}) == b"\x08\x01\x10\x0a"
    cust = ALL_MESSAGES["CustomControl"]
    assert encode_message(cust, {"data": b"\x01\x02"}) == b"\x0a\x02\x01\x02"


def test_all_messages_roundtrip():
    samples = {
        "KeyboardMouseControl": {"mouse_x": -5, "mouse_y": 10, "keyboard_value": 0x8000,
                                 "left_button_down": True},
        "CustomControl": {"data": bytes(range(30))},
        "GameStatus": {"current_round": 1, "total_rounds": 3, "current_stage": 4,
                       "stage_countdown_sec": -5, "game_result": 255},
        "GlobalUnitStatus": {"base_health": 2000, "robot_health": [100, 100, 100, 100],
                             "robot_bullets": [1, -2, 3], "total_damage_ally": 500},
        "GlobalLogisticsStatus": {"remaining_economy": 10, "total_economy_obtained": 1 << 40,
                                  "tech_level": 2, "encryption_level": 1},
        "GlobalSpecialMechanism": {"mechanism_id": [1, 2], "mechanism_time_sec": [-3, 5]},
        "Event": {"event_id": 9, "param": "1,2"},
        "RobotInjuryStat": {"total_damage": 100, "killer_id": 101},
        "RobotRespawnStatus": {"is_pending_respawn": True, "total_respawn_progress": 100,
                               "current_respawn_progress": 30, "gold_cost_for_respawn": 50},
        "RobotStaticStatus": {"robot_id": 7, "max_health": 100, "max_heat": 240,
                              "heat_cooldown_rate": 30.0, "max_power": 45},
        "RobotDynamicStatus": {"current_health": 80, "current_heat": 12.5,
                               "remaining_ammo": 88, "is_out_of_combat": False},
        "RobotModuleStatus": {"power_manager": 1, "rfid": 1, "armor": 1},
        "RobotPosition": {"x": 1.5, "y": 2.5, "z": 0.0, "yaw": 90.0, "robot_id": 7},
        "Buff": {"robot_id": 7, "buff_type": 1, "buff_level": 50, "buff_max_time": 30,
                 "buff_left_time": 10},
        "PenaltyInfo": {"penalty_type": 4, "penalty_effect_sec": 3, "total_penalty_num": 1},
        "RobotPathPlanInfo": {"intention": 1, "start_pos_x": 100, "start_pos_y": 200,
                              "offset_x": list(range(-3, 3)), "offset_y": [0] * 6,
                              "sender_id": 7},
        "MapClickCmd": {"is_send_all": 1, "robot_id": b"\x01\x02" + b"\x00" * 5,
                        "mode": 1, "enemy_id": 101, "ascii": 67, "type": 1,
                        "map_x": 1.0, "map_y": 2.0},
        "MapClickInfo": {"is_send_all": 0, "robot_id": bytes(7), "map_x": 3.0, "map_y": 4.0},
        "RadarInfoToClient": {"RadarSingleRobotInfo": [
            {"target_pos_x": 10, "target_pos_y": 20, "is_high_light": 0},
            {"target_pos_x": 30, "target_pos_y": 40, "is_high_light": 1},
        ]},
        "CustomByteBlock": {"data": bytes(64)},
        "AssemblyCommand": {"operation": 1, "difficulty": 4},
        "TechCoreMotionStateSync": {"maximum_difficulty_level": 4, "basic_state": 3,
                                    "remain_time_all": 120},
        "RobotPerformanceSelectionCommand": {"shooter": 1, "chassis": 2, "sentry_control": 1},
        "RobotPerformanceSelectionSync": {"shooter": 1, "chassis": 2, "sentry_control": 1},
        "CommonCommand": {"cmd_type": 1, "param": 10},
        "HeroDeployModeEventCommand": {"mode": 1},
        "DeployModeStatusSync": {"status": 1},
        "RuneActivateCommand": {"activate": 1},
        "RuneStatusSync": {"rune_status": 3, "activated_arms": 10, "average_rings": 9.6},
        "SentryStatusSync": {"posture_id": 1, "is_weakened": True, "is_powered": False},
        "DartCommand": {"target_id": 2, "open": True, "launch_confirm": False},
        "DartSelectTargetStatusSync": {"target_id": 2, "open": 2},
        "SentryCtrlCommand": {"command_id": 7},
        "SentryCtrlResult": {"command_id": 7, "result_code": 0},
        "AirSupportCommand": {"command_id": 1},
        "AirSupportStatusSync": {"airsupport_status": 1, "left_time": 30, "cost_coins": 0,
                                 "is_being_targeted": 0, "shooter_status": 1},
    }
    assert set(samples) == set(ALL_MESSAGES)
    for name, values in samples.items():
        schema = ALL_MESSAGES[name]
        data = encode_message(schema, values)
        dec = decode_message(schema, data)
        for key, expected in values.items():
            if isinstance(expected, float):
                assert math.isclose(dec[key], expected, rel_tol=1e-5), (name, key)
            else:
                assert dec.get(key) == expected, (name, key)
