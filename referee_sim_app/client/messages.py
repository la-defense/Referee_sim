"""官方《RoboMaster 2026 通信协议 V2.0.0》自定义客户端消息定义（2.1/2.2 节）。"""

from __future__ import annotations

from dataclasses import dataclass

from .proto import FieldSpec, MessageSchema


def M(name: str, *fields) -> MessageSchema:
    return MessageSchema(name=name, fields=tuple(fields))


def f(number: int, name: str, kind: str, **kw) -> FieldSpec:
    return FieldSpec(number=number, name=name, kind=kind, **kw)


RadarSingleRobotInfo = M(
    "RadarSingleRobotInfo",
    f(1, "target_pos_x", "u32"),
    f(2, "target_pos_y", "u32"),
    f(3, "is_high_light", "u32"),
)

ALL_MESSAGES: dict[str, MessageSchema] = {
    # 自定义客户端 → 机器人（发送）
    "KeyboardMouseControl": M(
        "KeyboardMouseControl",
        f(1, "mouse_x", "i32"), f(2, "mouse_y", "i32"), f(3, "mouse_z", "i32"),
        f(4, "left_button_down", "bool"), f(5, "right_button_down", "bool"),
        f(6, "keyboard_value", "u32"), f(7, "mid_button_down", "bool"),
    ),
    "CustomControl": M("CustomControl", f(1, "data", "bytes")),
    "MapClickCmd": M(
        "MapClickCmd",
        f(1, "is_send_all", "u32"), f(2, "robot_id", "bytes"), f(3, "mode", "u32"),
        f(4, "enemy_id", "u32"), f(5, "ascii", "u32"), f(6, "type", "u32"),
        f(7, "map_x", "f32"), f(8, "map_y", "f32"),
    ),
    "AssemblyCommand": M(
        "AssemblyCommand", f(1, "operation", "u32"), f(2, "difficulty", "u32"),
    ),
    "RobotPerformanceSelectionCommand": M(
        "RobotPerformanceSelectionCommand",
        f(1, "shooter", "u32"), f(2, "chassis", "u32"), f(3, "sentry_control", "u32"),
    ),
    "CommonCommand": M("CommonCommand", f(1, "cmd_type", "u32"), f(2, "param", "u32")),
    "HeroDeployModeEventCommand": M("HeroDeployModeEventCommand", f(1, "mode", "u32")),
    "RuneActivateCommand": M("RuneActivateCommand", f(1, "activate", "u32")),
    "DartCommand": M(
        "DartCommand",
        f(1, "target_id", "u32"), f(2, "open", "bool"), f(3, "launch_confirm", "bool"),
    ),
    "SentryCtrlCommand": M("SentryCtrlCommand", f(1, "command_id", "u32")),
    "AirSupportCommand": M("AirSupportCommand", f(1, "command_id", "u32")),
    # 服务器 → 自定义客户端（接收）
    "GameStatus": M(
        "GameStatus",
        f(1, "current_round", "u32"), f(2, "total_rounds", "u32"),
        f(3, "red_score", "u32"), f(4, "blue_score", "u32"), f(5, "current_stage", "u32"),
        f(6, "stage_countdown_sec", "i32"), f(7, "stage_elapsed_sec", "i32"),
        f(8, "is_paused", "bool"), f(9, "game_result", "u32"), f(10, "end_reason", "u32"),
    ),
    "GlobalUnitStatus": M(
        "GlobalUnitStatus",
        f(1, "base_health", "u32"), f(2, "base_status", "u32"), f(3, "base_shield", "u32"),
        f(4, "outpost_health", "u32"), f(5, "outpost_status", "u32"),
        f(6, "enemy_base_health", "u32"), f(7, "enemy_base_status", "u32"),
        f(8, "enemy_base_shield", "u32"), f(9, "enemy_outpost_health", "u32"),
        f(10, "enemy_outpost_status", "u32"),
        f(11, "robot_health", "u32", repeated=True),
        f(12, "robot_bullets", "i32", repeated=True),
        f(13, "total_damage_ally", "u32"), f(14, "total_damage_enemy", "u32"),
    ),
    "GlobalLogisticsStatus": M(
        "GlobalLogisticsStatus",
        f(1, "remaining_economy", "u32"), f(2, "total_economy_obtained", "u64"),
        f(3, "tech_level", "u32"), f(4, "encryption_level", "u32"),
    ),
    "GlobalSpecialMechanism": M(
        "GlobalSpecialMechanism",
        f(1, "mechanism_id", "u32", repeated=True),
        f(2, "mechanism_time_sec", "i32", repeated=True),
    ),
    "Event": M("Event", f(1, "event_id", "i32"), f(2, "param", "string")),
    "RobotInjuryStat": M(
        "RobotInjuryStat",
        f(1, "total_damage", "u32"), f(2, "collision_damage", "u32"),
        f(3, "small_projectile_damage", "u32"), f(4, "large_projectile_damage", "u32"),
        f(5, "dart_splash_damage", "u32"), f(6, "module_offline_damage", "u32"),
        f(7, "offline_damage", "u32"), f(8, "penalty_damage", "u32"),
        f(9, "server_kill_damage", "u32"), f(10, "killer_id", "u32"),
    ),
    "RobotRespawnStatus": M(
        "RobotRespawnStatus",
        f(1, "is_pending_respawn", "bool"), f(2, "total_respawn_progress", "u32"),
        f(3, "current_respawn_progress", "u32"), f(4, "can_free_respawn", "bool"),
        f(5, "gold_cost_for_respawn", "u32"), f(6, "can_pay_for_respawn", "bool"),
    ),
    "RobotStaticStatus": M(
        "RobotStaticStatus",
        f(1, "connection_state", "u32"), f(2, "field_state", "u32"),
        f(3, "alive_state", "u32"), f(4, "robot_id", "u32"), f(5, "robot_type", "u32"),
        f(6, "performance_system_shooter", "u32"), f(7, "performance_system_chassis", "u32"),
        f(8, "level", "u32"), f(9, "max_health", "u32"), f(10, "max_heat", "u32"),
        f(11, "heat_cooldown_rate", "f32"), f(12, "max_power", "u32"),
        f(13, "max_buffer_energy", "u32"), f(14, "max_chassis_energy", "u32"),
    ),
    "RobotDynamicStatus": M(
        "RobotDynamicStatus",
        f(1, "current_health", "u32"), f(2, "current_heat", "f32"),
        f(3, "last_projectile_fire_rate", "f32"), f(4, "current_chassis_energy", "u32"),
        f(5, "current_buffer_energy", "u32"), f(6, "current_experience", "u32"),
        f(7, "experience_for_upgrade", "u32"), f(8, "total_projectiles_fired", "u32"),
        f(9, "remaining_ammo", "u32"), f(10, "is_out_of_combat", "bool"),
        f(11, "out_of_combat_countdown", "u32"), f(12, "can_remote_heal", "bool"),
        f(13, "can_remote_ammo", "bool"),
    ),
    "RobotModuleStatus": M(
        "RobotModuleStatus",
        f(1, "power_manager", "u32"), f(2, "rfid", "u32"), f(3, "light_strip", "u32"),
        f(4, "small_shooter", "u32"), f(5, "big_shooter", "u32"), f(6, "uwb", "u32"),
        f(7, "armor", "u32"), f(8, "video_transmission", "u32"), f(9, "capacitor", "u32"),
        f(10, "main_controller", "u32"), f(11, "laser_detection_module", "u32"),
    ),
    "RobotPosition": M(
        "RobotPosition",
        f(1, "x", "f32"), f(2, "y", "f32"), f(3, "z", "f32"), f(4, "yaw", "f32"),
        f(5, "robot_id", "u32"),
    ),
    "Buff": M(
        "Buff",
        f(1, "robot_id", "u32"), f(2, "buff_type", "u32"), f(3, "buff_level", "i32"),
        f(4, "buff_max_time", "u32"), f(5, "buff_left_time", "u32"),
    ),
    "PenaltyInfo": M(
        "PenaltyInfo",
        f(1, "penalty_type", "u32"), f(2, "penalty_effect_sec", "u32"),
        f(3, "total_penalty_num", "u32"),
    ),
    "RobotPathPlanInfo": M(
        "RobotPathPlanInfo",
        f(1, "intention", "u32"), f(2, "start_pos_x", "u32"), f(3, "start_pos_y", "u32"),
        f(4, "offset_x", "i32", repeated=True, packed=True),
        f(5, "offset_y", "i32", repeated=True, packed=True),
        f(6, "sender_id", "u32"),
    ),
    "MapClickInfo": M(
        "MapClickInfo",
        f(1, "is_send_all", "u32"), f(2, "robot_id", "bytes"), f(3, "mode", "u32"),
        f(4, "enemy_id", "u32"), f(5, "ascii", "u32"), f(6, "type", "u32"),
        f(7, "map_x", "f32"), f(8, "map_y", "f32"),
    ),
    "RadarInfoToClient": M(
        "RadarInfoToClient",
        f(1, "RadarSingleRobotInfo", "message", repeated=True, sub=RadarSingleRobotInfo),
    ),
    "CustomByteBlock": M("CustomByteBlock", f(1, "data", "bytes")),
    "TechCoreMotionStateSync": M(
        "TechCoreMotionStateSync",
        f(1, "maximum_difficulty_level", "u32"), f(2, "basic_state", "u32"),
        f(3, "putin_state", "u32"), f(4, "move_state", "u32"),
        f(5, "rotate_state", "u32"), f(6, "enemy_core_status", "u32"),
        f(7, "remain_time_all", "u32"), f(8, "remain_time_step", "u32"),
    ),
    "RobotPerformanceSelectionSync": M(
        "RobotPerformanceSelectionSync",
        f(1, "shooter", "u32"), f(2, "chassis", "u32"), f(3, "sentry_control", "u32"),
    ),
    "DeployModeStatusSync": M("DeployModeStatusSync", f(1, "status", "u32")),
    "RuneStatusSync": M(
        "RuneStatusSync",
        f(1, "rune_status", "u32"), f(2, "activated_arms", "u32"),
        f(3, "average_rings", "f32"),
    ),
    "SentryStatusSync": M(
        "SentryStatusSync",
        f(1, "posture_id", "u32"), f(2, "is_weakened", "bool"), f(3, "is_powered", "bool"),
    ),
    "DartSelectTargetStatusSync": M(
        "DartSelectTargetStatusSync", f(1, "target_id", "u32"), f(2, "open", "u32"),
    ),
    "SentryCtrlResult": M(
        "SentryCtrlResult", f(1, "command_id", "u32"), f(2, "result_code", "u32"),
    ),
    "AirSupportStatusSync": M(
        "AirSupportStatusSync",
        f(1, "airsupport_status", "u32"), f(2, "left_time", "u32"),
        f(3, "cost_coins", "u32"), f(4, "is_being_targeted", "u32"),
        f(5, "shooter_status", "u32"),
    ),
}


@dataclass(frozen=True)
class TopicInfo:
    name: str
    direction: str  # send=客户端→服务器, recv=服务器→客户端
    freq: str
    schema: MessageSchema


MESSAGE_TOPICS: dict[str, TopicInfo] = {}
_SEND_TOPICS = [
    "KeyboardMouseControl", "CustomControl", "MapClickCmd", "AssemblyCommand",
    "RobotPerformanceSelectionCommand", "CommonCommand", "HeroDeployModeEventCommand",
    "RuneActivateCommand", "DartCommand", "SentryCtrlCommand", "AirSupportCommand",
]
_RECV_TOPICS = [
    "GameStatus", "GlobalUnitStatus", "GlobalLogisticsStatus", "GlobalSpecialMechanism",
    "Event", "RobotInjuryStat", "RobotRespawnStatus", "RobotStaticStatus",
    "RobotDynamicStatus", "RobotModuleStatus", "RobotPosition", "Buff", "PenaltyInfo",
    "RobotPathPlanInfo", "MapClickInfo", "RadarInfoToClient", "CustomByteBlock",
    "TechCoreMotionStateSync", "RobotPerformanceSelectionSync", "DeployModeStatusSync",
    "RuneStatusSync", "SentryStatusSync", "DartSelectTargetStatusSync",
    "SentryCtrlResult", "AirSupportStatusSync",
]
for _name in _SEND_TOPICS:
    MESSAGE_TOPICS[_name] = TopicInfo(_name, "send", "触发式(≤10Hz 或按规则)", ALL_MESSAGES[_name])
for _name in _RECV_TOPICS:
    MESSAGE_TOPICS[_name] = TopicInfo(_name, "recv", "按表 2-1", ALL_MESSAGES[_name])


def topic_schema(topic: str) -> MessageSchema | None:
    info = MESSAGE_TOPICS.get(topic)
    return info.schema if info else None
