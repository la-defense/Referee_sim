"""全流程比赛场景模拟（纯逻辑，可测试）。

按官方比赛阶段推进：未开始 → 准备 → 十五秒自检 → 五秒倒计时 → 比赛 → 结算，
并随时间变化血量/热量/功率/缓冲能量/发弹量/金币/增益等数据，
触发伤害、射击、判罚、比赛结果等一次性事件。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class MatchConfig:
    robot_id: int = 7
    max_hp: int = 100
    heat_limit: int = 240
    cooling_value: int = 30
    power_limit: int = 45
    bullet_speed_limit: float = 30.0
    idle_duration: float = 10.0
    prep_duration: float = 120.0
    selfcheck_duration: float = 15.0
    countdown_duration: float = 5.0
    match_duration: float = 300.0
    settlement_duration: float = 10.0
    shoot_interval: float = 0.6
    hurt_interval: float = 8.0
    warning_after: float = 20.0


PHASE_NAMES = {
    0: "未开始",
    1: "准备阶段",
    2: "十五秒自检",
    3: "五秒倒计时",
    4: "比赛中",
    5: "比赛结算",
    6: "比赛结束",
}


class MatchFlow:
    def __init__(self, config: MatchConfig | None = None) -> None:
        self.config = config or MatchConfig()
        self.phase = 0
        self.phase_elapsed = 0.0
        self.total_elapsed = 0.0
        self._shoot_timer = self.config.shoot_interval
        self._hurt_timer = self.config.hurt_interval
        self._warned = False
        self._result_sent = False
        self._reset_values()

    def _reset_values(self) -> None:
        self.current_hp = float(self.config.max_hp)
        self.damage_difference = 0
        self.heat_17mm = 0
        self.heat_42mm = 0
        self.power = 0.0
        self.buffer_energy = 0
        self.allowance_17mm = 100
        self.allowance_42mm = 0
        self.gold_coin = 0
        self.recovery_buff = 0
        self.cooling_buff = 0
        self.defence_buff = 0
        self.vulnerability_buff = 0
        self.attack_buff = 0
        self.remaining_energy = 0x7F
        self.rfid_status = 0
        self.rfid_status_2 = 0
        self.dart_status = 1
        self.sentry_info = 0
        self.sentry_info_2 = 0
        self.sentry_info_3 = 0
        self.mark_progress = 0
        self.radar_info = 0x10
        self.warning_level = 0
        self.warning_count = 0
        self.winner = 0

    def reset(self) -> None:
        self.phase = 0
        self.phase_elapsed = 0.0
        self.total_elapsed = 0.0
        self._shoot_timer = self.config.shoot_interval
        self._hurt_timer = self.config.hurt_interval
        self._warned = False
        self._result_sent = False
        self._reset_values()

    @property
    def phase_name(self) -> str:
        return PHASE_NAMES.get(self.phase, f"未知({self.phase})")

    @property
    def phase_duration(self) -> float:
        return [
            self.config.idle_duration,
            self.config.prep_duration,
            self.config.selfcheck_duration,
            self.config.countdown_duration,
            self.config.match_duration,
            self.config.settlement_duration,
            0.0,
        ][self.phase]

    @property
    def phase_remain(self) -> float:
        return max(0.0, self.phase_duration - self.phase_elapsed)

    @property
    def game_progress(self) -> int:
        if self.phase >= 5:
            return 5
        return self.phase

    def update(self, dt: float) -> list[dict]:
        """推进 dt 秒，返回本步需要触发的事件列表。"""
        events: list[dict] = []
        if dt <= 0 or self.phase >= 6:
            return events
        self.total_elapsed += dt
        self.phase_elapsed += dt

        if self.phase == 4:
            self._update_match(dt, events)

        if self.phase_elapsed >= self.phase_duration:
            self.phase += 1
            self.phase_elapsed = 0.0
            events.append({"type": "phase", "phase": self.phase})
            if self.phase == 5:
                self.winner = 1 if self.damage_difference >= 0 else 2
                events.append({"type": "result", "winner": self.winner})
            elif self.phase == 6:
                self._reset_values()
        return events

    def _update_match(self, dt: float, events: list[dict]) -> None:
        t = self.total_elapsed
        elapsed = self.phase_elapsed

        # 血量缓慢下降，受伤害时额外扣血
        self.current_hp = max(
            15.0, self.config.max_hp - (elapsed / 300.0) * self.config.max_hp * 0.4
        )
        self._hurt_timer -= dt
        if self._hurt_timer <= 0:
            self._hurt_timer = self.config.hurt_interval
            self.current_hp = max(15.0, self.current_hp - 5.0)
            events.append({"type": "hurt", "armor_id": (int(t) % 4) + 1, "hurt_type": 0})

        # 射击热量：按射击间隔累积，同时按冷却值衰减
        self.heat_17mm = max(0, self.heat_17mm - self.config.cooling_value * dt)
        self._shoot_timer -= dt
        if self._shoot_timer <= 0:
            self._shoot_timer = self.config.shoot_interval
            self.heat_17mm = min(self.config.heat_limit, self.heat_17mm + 8)
            speed = self.config.bullet_speed_limit + 2.0 * math.sin(t * 2.0)
            events.append({"type": "shoot", "bullet_type": 2, "shooter_number": 1,
                           "frequency": 10, "speed": speed})

        # 底盘功率/缓冲能量波动
        self.power = 22.0 + 12.0 * math.sin(t * 0.7) + 3.0 * math.sin(t * 3.1)
        self.power = max(0.0, min(float(self.config.power_limit), self.power))
        self.buffer_energy = int(60 + 20 * math.sin(t * 0.4))

        # 发弹量消耗、金币累积、伤害差变化
        self.allowance_17mm = max(0, 100 - int(elapsed / 3.0))
        self.gold_coin = int(elapsed)
        self.damage_difference = int(elapsed / 5.0)

        # 增益阶段性变化
        self.recovery_buff = 10 if elapsed > 90 else 0
        self.attack_buff = 50 if elapsed > 60 else 0
        self.defence_buff = 20 if elapsed > 120 else 0
        self.remaining_energy = max(0x01, 0x7F - int(elapsed / 10.0))

        # RFID/哨兵/雷达位域随时间点亮
        self.rfid_status = (1 << (int(t) % 10)) & 0xFFFFFFFF
        self.mark_progress = 1 << (int(t) % 12)
        self.sentry_info_2 = ((int(elapsed / 30.0) % 3 + 1) << 12)

        # 判罚事件
        if not self._warned and elapsed >= self.config.warning_after:
            self._warned = True
            self.warning_level = 2
            self.warning_count = 1
            events.append({"type": "warning", "level": 2, "count": 1})

    def values(self) -> dict:
        """供周期帧 builder 使用的当前数据快照。"""
        remain = int(math.ceil(self.phase_remain))
        return {
            "game_type": 1,
            "game_progress": self.game_progress,
            "stage_remain_time": max(0, remain),
            "robot_id": self.config.robot_id,
            "robot_level": 1,
            "current_hp": max(0, int(self.current_hp)),
            "maximum_hp": self.config.max_hp,
            "shooter_barrel_cooling_value": self.config.cooling_value,
            "shooter_barrel_heat_limit": self.config.heat_limit,
            "chassis_power_limit": self.config.power_limit,
            "bullet_speed_limit": self.config.bullet_speed_limit,
            "gimbal_output": 1,
            "chassis_output": 1,
            "shooter_output": 1,
            "buffer_energy": max(0, self.buffer_energy),
            "shooter_17mm_barrel_heat": max(0, int(self.heat_17mm)),
            "shooter_42mm_barrel_heat": max(0, int(self.heat_42mm)),
            "damage_difference": self.damage_difference,
            "ally_1_robot_hp": self.config.max_hp,
            "ally_2_robot_hp": self.config.max_hp,
            "ally_3_robot_hp": self.config.max_hp,
            "ally_4_robot_hp": max(0, int(self.current_hp)),
            "ally_7_robot_hp": self.config.max_hp,
            "ally_outpost_hp": 600,
            "ally_base_hp": 2000,
            "enemy_outpost_hp": 600,
            "enemy_base_hp": 2000,
            "projectile_allowance_17mm": self.allowance_17mm,
            "projectile_allowance_42mm": self.allowance_42mm,
            "remaining_gold_coin": self.gold_coin,
            "projectile_allowance_fortress": 0,
            "recovery_buff": self.recovery_buff,
            "cooling_buff": self.cooling_buff,
            "defence_buff": self.defence_buff,
            "vulnerability_buff": self.vulnerability_buff,
            "attack_buff": self.attack_buff,
            "remaining_energy": self.remaining_energy,
            "rfid_status": self.rfid_status,
            "rfid_status_2": self.rfid_status_2,
            "dart_launch_opening_status": self.dart_status,
            "target_change_time": 0,
            "latest_launch_cmd_time": 0,
            "sentry_info": self.sentry_info,
            "sentry_info_2": self.sentry_info_2,
            "sentry_info_3": self.sentry_info_3,
            "mark_progress": self.mark_progress,
            "radar_info": self.radar_info,
            "event_data": self.rfid_status & 0x3FF,
            "dart_remaining_time": 0,
            "dart_info": 0,
            "level": self.warning_level,
            "offending_robot_id": self.config.robot_id,
            "count": self.warning_count,
            "hero_x": 1.5 + math.sin(self.total_elapsed * 0.2) * 0.5,
            "hero_y": 2.0 + math.cos(self.total_elapsed * 0.2) * 0.3,
            "engineer_x": 3.0,
            "engineer_y": 3.0,
            "standard_3_x": 4.0,
            "standard_3_y": 4.0,
            "standard_4_x": 5.0,
            "standard_4_y": 5.0,
            "x": 1.5 + math.sin(self.total_elapsed * 0.2) * 0.5,
            "y": 2.0 + math.cos(self.total_elapsed * 0.2) * 0.3,
            "angle": (self.total_elapsed * 30.0) % 360.0,
        }
