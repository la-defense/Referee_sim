"""官方 RoboMaster 2026 通信协议 V2.0.0 命令定义。

所有长度、字段、频率均以官方文档（20260626）为准；文档内部矛盾处（如 0x0203、
0x0307 的长度）按详细字段表实现，并在注释/README 中说明。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

FORMATS = {
    "u8": "<B",
    "u16": "<H",
    "u32": "<I",
    "u64": "<Q",
    "i8": "<b",
    "i16": "<h",
    "i32": "<i",
    "f32": "<f",
}


@dataclass
class Field:
    name: str
    ctype: str
    size: int = 0  # 仅 bytes 类型使用；0 表示动态长度
    label: str = ""
    unit: str = ""
    default: object = 0
    choices: dict[int, str] | None = None
    note: str = ""
    hex: bool = False


@dataclass
class BitField:
    name: str
    lsb: int
    width: int
    label: str = ""
    default: int = 0
    choices: dict[int, str] | None = None
    note: str = ""


@dataclass
class BitGroup:
    container_name: str
    size: int  # 字节数
    bits: list[BitField]
    label: str = ""
    note: str = ""


@dataclass
class CommandSpec:
    cmd_id: int
    name: str
    length: int
    direction: str  # down=裁判→机器人, up=机器人→裁判, both, radar
    freq: float | None  # Hz；None 表示触发式
    chunks: list[Field | BitGroup]
    note: str = ""

    @property
    def label(self) -> str:
        return f"0x{self.cmd_id:04X} {self.name}"

    @property
    def minimal_length(self) -> int:
        n = 0
        for c in self.chunks:
            if isinstance(c, BitGroup):
                n += c.size
            elif c.ctype == "bytes" and c.size:
                n += c.size
            elif c.ctype != "bytes":
                n += struct.calcsize(FORMATS[c.ctype])
        return n


def f(name: str, ctype: str, **kw) -> Field:
    return Field(name=name, ctype=ctype, **kw)


def bf(name: str, lsb: int, width: int, **kw) -> BitField:
    return BitField(name=name, lsb=lsb, width=width, **kw)


def _commands() -> dict[int, CommandSpec]:
    cmds: dict[int, CommandSpec] = {}

    def add(spec: CommandSpec) -> None:
        cmds[spec.cmd_id] = spec

    add(CommandSpec(
        0x0001, "比赛状态数据", 11, "down", 1.0,
        [
            BitGroup("game_status", 1, [
                bf("game_type", 0, 4, label="比赛类型", default=1,
                   choices={1: "超级对抗赛", 2: "高校单项赛", 3: "ICRA AI挑战赛",
                            4: "联盟赛 3V3", 5: "联盟赛步兵对抗"}),
                bf("game_progress", 4, 4, label="比赛阶段", default=4,
                   choices={0: "未开始", 1: "准备阶段", 2: "十五秒自检", 3: "五秒倒计时",
                            4: "比赛中", 5: "比赛结算"}),
            ], label="比赛类型/阶段"),
            f("stage_remain_time", "u16", label="阶段剩余时间", unit="s", default=300),
            f("sync_timestamp", "u64", label="同步时间戳(UNIX)", default=0,
              note="连接裁判系统 NTP 后生效"),
        ],
        note="固定 1Hz",
    ))
    add(CommandSpec(
        0x0002, "比赛结果数据", 1, "down", None,
        [f("winner", "u8", label="胜方", default=1,
           choices={0: "平局", 1: "红方胜利", 2: "蓝方胜利"})],
        note="比赛结束触发发送",
    ))
    add(CommandSpec(
        0x0003, "机器人血量数据", 20, "down", 3.0,
        [
            f("ally_1_robot_hp", "u16", label="己方1号英雄血量", default=100),
            f("ally_2_robot_hp", "u16", label="己方2号工程血量", default=100),
            f("ally_3_robot_hp", "u16", label="己方3号步兵血量", default=100),
            f("ally_4_robot_hp", "u16", label="己方4号步兵血量", default=100),
            f("damage_difference", "i16", label="全队伤害差(己-对)", default=0),
            f("ally_7_robot_hp", "u16", label="己方7号哨兵血量", default=100),
            f("ally_outpost_hp", "u16", label="己方前哨站血量", default=600),
            f("ally_base_hp", "u16", label="己方基地血量", default=2000),
            f("enemy_outpost_hp", "u16", label="对方前哨站血量", default=600),
            f("enemy_base_hp", "u16", label="对方基地血量", default=2000),
        ],
        note="固定 3Hz；未上场/被罚下机器人血量为 0",
    ))
    add(CommandSpec(
        0x0101, "场地事件数据", 4, "down", 1.0,
        [f("event_data", "u32", label="事件位域", hex=True, default=0,
           note="bit0 补给区；bit3-4 小能量机关；bit5-6 大能量机关；bit7-8 中央高地；bit9-10 梯形高地；bit11-19 飞镖命中时间；bit20-22 飞镖命中目标；bit23-24 中心增益点；bit25-26 堡垒增益点；bit27-28 前哨站增益点；bit29 基地增益点")],
        note="固定 1Hz",
    ))
    add(CommandSpec(
        0x0104, "裁判警告数据", 3, "down", 1.0,
        [
            f("level", "u8", label="判罚等级", default=0,
              choices={1: "双方黄牌", 2: "黄牌", 3: "红牌", 4: "判负"}),
            f("offending_robot_id", "u8", label="违规机器人 ID", default=0),
            f("count", "u8", label="违规次数", default=0),
        ],
        note="判罚/判负时触发，其余时间 1Hz",
    ))
    add(CommandSpec(
        0x0105, "飞镖发射相关数据", 3, "down", 1.0,
        [
            f("dart_remaining_time", "u8", label="飞镖发射剩余时间", unit="s", default=0),
            f("dart_info", "u16", label="飞镖信息位域", hex=True, default=0,
              note="bit0-2 最近命中目标；bit3-5 对方被击中累计次数；bit6-8 选定击打目标"),
        ],
        note="固定 1Hz",
    ))
    add(CommandSpec(
        0x0201, "机器人性能体系数据", 17, "down", 10.0,
        [
            f("robot_id", "u8", label="本机器人 ID", default=7,
              choices={1: "红英雄", 2: "红工程", 3: "红步兵3", 4: "红步兵4", 5: "红步兵5",
                       6: "红空中", 7: "红哨兵", 9: "红雷达",
                       101: "蓝英雄", 102: "蓝工程", 103: "蓝步兵3", 104: "蓝步兵4",
                       105: "蓝步兵5", 106: "蓝空中", 107: "蓝哨兵", 109: "蓝雷达"}),
            f("robot_level", "u8", label="机器人等级", default=1),
            f("current_hp", "u16", label="当前血量", default=100),
            f("maximum_hp", "u16", label="血量上限", default=100),
            f("shooter_barrel_cooling_value", "u16", label="射击热量冷却值", unit="/s", default=0),
            f("shooter_barrel_heat_limit", "u16", label="射击热量上限", default=240),
            f("chassis_power_limit", "u16", label="底盘功率上限", unit="W", default=45),
            f("bullet_speed_limit", "f32", label="射击初速度上限", unit="m/s", default=30.0),
            BitGroup("power_output", 1, [
                bf("gimbal_output", 0, 1, label="Gimbal 口 24V 输出", default=1),
                bf("chassis_output", 1, 1, label="Chassis 口 24V 输出", default=1),
                bf("shooter_output", 2, 1, label="Shooter 口 24V 输出", default=1),
            ], label="电源管理输出"),
        ],
        note="固定 10Hz",
    ))
    add(CommandSpec(
        0x0202, "实时底盘缓冲能量和射击热量", 14, "down", 10.0,
        [
            f("reserved_1", "u16", label="保留位1", default=0, hex=True),
            f("reserved_2", "u16", label="保留位2", default=0, hex=True),
            f("reserved_3", "f32", label="保留位3", default=0.0),
            f("buffer_energy", "u16", label="缓冲能量", unit="J", default=60),
            f("shooter_17mm_barrel_heat", "u16", label="17mm 射击热量", default=0),
            f("shooter_42mm_barrel_heat", "u16", label="42mm 射击热量", default=0),
        ],
        note="固定 10Hz",
    ))
    add(CommandSpec(
        0x0203, "机器人位置数据", 16, "down", 1.0,
        [
            f("x", "f32", label="本机 X 坐标", unit="m", default=0.0),
            f("y", "f32", label="本机 Y 坐标", unit="m", default=0.0),
            f("angle", "f32", label="测速模块朝向", unit="°", default=0.0),
            f("reserved", "u32", label="保留位(文档长度16B, 字段表仅12B)", hex=True, default=0),
        ],
        note="固定 1Hz；官方文档命令表长度 16B 与字段表 12B 矛盾，此处按 16B 实现，保留 4B",
    ))
    add(CommandSpec(
        0x0204, "机器人增益和底盘能量", 8, "down", 3.0,
        [
            f("recovery_buff", "u8", label="回血增益", unit="%", default=0),
            f("cooling_buff", "u16", label="热量冷却增益", unit="/s", default=0),
            f("defence_buff", "u8", label="防御增益", unit="%", default=0),
            f("vulnerability_buff", "u8", label="负防御增益", unit="%", default=0),
            f("attack_buff", "u16", label="攻击增益", unit="%", default=0),
            f("remaining_energy", "u8", label="剩余能量反馈", hex=True, default=0,
              note="bit0-6 剩余能量比例；bit0≥125%、bit1≥100%、bit2≥50%、bit3≥30%、bit4≥15%、bit5≥5%、bit6≥1%"),
        ],
        note="固定 3Hz",
    ))
    add(CommandSpec(
        0x0206, "伤害状态数据", 1, "down", None,
        [BitGroup("hurt", 1, [
            bf("armor_id", 0, 4, label="装甲模块/测速模块 ID", default=0),
            bf("hurt_type", 4, 4, label="血量变化类型", default=0,
               choices={0: "弹丸攻击", 1: "模块离线", 5: "撞击"}),
        ], label="伤害状态")],
        note="伤害发生后发送；实际是否生效以服务器判定为准",
    ))
    add(CommandSpec(
        0x0207, "实时射击数据", 7, "down", None,
        [
            f("bullet_type", "u8", label="弹丸类型", default=2,
              choices={2: "17mm 弹丸(bit1)", 4: "42mm 弹丸(bit2)"}),
            f("shooter_number", "u8", label="发射机构 ID", default=1,
              choices={1: "17mm 发射机构", 3: "42mm 发射机构"}),
            f("launching_frequency", "u8", label="弹丸射速", unit="Hz", default=10),
            f("initial_speed", "f32", label="弹丸初速度", unit="m/s", default=30.0),
        ],
        note="弹丸发射后发送",
    ))
    add(CommandSpec(
        0x0208, "允许发弹量与剩余金币", 8, "down", 10.0,
        [
            f("projectile_allowance_17mm", "u16", label="17mm 允许发弹量", default=100),
            f("projectile_allowance_42mm", "u16", label="42mm 允许发弹量", default=0),
            f("remaining_gold_coin", "u16", label="剩余金币", default=0),
            f("projectile_allowance_fortress", "u16", label="堡垒储备 17mm 发弹量", default=0),
        ],
        note="固定 10Hz",
    ))
    add(CommandSpec(
        0x0209, "RFID 模块状态", 5, "down", 3.0,
        [
            f("rfid_status", "u32", label="RFID 状态位域1", hex=True, default=0,
              note="bit0 己方基地；bit1-2 中央高地；bit3-4 梯形高地；bit5-8 飞坡；bit9-12 中央高地上下；bit13-16 公路上下；bit17 堡垒；bit18 前哨站；bit19-20 补给区；bit21-22 装配点；bit23 中心增益点；bit24-25 对方堡垒/前哨站；bit26-31 隧道"),
            f("rfid_status_2", "u8", label="RFID 状态位域2", hex=True, default=0,
              note="bit0-5 对方隧道增益点"),
        ],
        note="固定 3Hz；赛外检测到 RFID 对应值仍为 0",
    ))
    add(CommandSpec(
        0x020A, "飞镖选手端指令", 6, "down", 3.0,
        [
            f("dart_launch_opening_status", "u8", label="飞镖发射站状态", default=1,
              choices={0: "已开启", 1: "关闭", 2: "正在开启/关闭中"}),
            f("reserved", "u8", label="保留位", hex=True, default=0),
            f("target_change_time", "u16", label="切换目标时剩余时间", unit="s", default=0),
            f("latest_launch_cmd_time", "u16", label="最后发射指令时剩余时间", unit="s", default=0),
        ],
        note="固定 3Hz",
    ))
    add(CommandSpec(
        0x020B, "地面机器人位置数据", 40, "down", 1.0,
        [
            f("hero_x", "f32", label="己方英雄 X", unit="m", default=0.0),
            f("hero_y", "f32", label="己方英雄 Y", unit="m", default=0.0),
            f("engineer_x", "f32", label="己方工程 X", unit="m", default=0.0),
            f("engineer_y", "f32", label="己方工程 Y", unit="m", default=0.0),
            f("standard_3_x", "f32", label="己方步兵3 X", unit="m", default=0.0),
            f("standard_3_y", "f32", label="己方步兵3 Y", unit="m", default=0.0),
            f("standard_4_x", "f32", label="己方步兵4 X", unit="m", default=0.0),
            f("standard_4_y", "f32", label="己方步兵4 Y", unit="m", default=0.0),
            f("reserved_1", "f32", label="保留位1", default=0.0),
            f("reserved_2", "f32", label="保留位2", default=0.0),
        ],
        note="固定 1Hz；发送给己方哨兵",
    ))
    add(CommandSpec(
        0x020C, "雷达标记进度", 2, "down", 1.0,
        [f("mark_progress", "u16", label="标记进度位域", hex=True, default=0,
           note="bit0-5 对方英雄/工程/步兵/空中/哨兵易伤；bit6-11 己方特殊标识；bit12-15 空中机器人激光瞄准/反制状态")],
        note="固定 1Hz",
    ))
    add(CommandSpec(
        0x020D, "哨兵自主决策信息同步", 14, "down", 1.0,
        [
            f("sentry_info", "u32", label="哨兵信息1", hex=True, default=0,
              note="bit0-10 成功兑换发弹量；bit11-14 远程兑换发弹量次数；bit15-18 远程兑换血量次数；bit19 可免费复活；bit20 可立即复活；bit21-30 立即复活金币"),
            f("sentry_info_2", "u16", label="哨兵信息2", hex=True, default=0,
              note="bit0 脱战；bit1-11 剩余可兑换17mm发弹量；bit12-13 姿态；bit14 能量机关可激活；bit15 强化姿态"),
            f("sentry_info_3", "u64", label="哨兵信息3", hex=True, default=0,
              note="bit0-7 进攻弱化前时长；bit8-15 防御弱化前时长；bit16-23 移动弱化前时长；bit32-39 强化进攻时长；bit40-47 强化防御时长；bit48-55 强化移动时长"),
        ],
        note="固定 1Hz",
    ))
    add(CommandSpec(
        0x020E, "雷达自主决策信息同步", 1, "down", 1.0,
        [f("radar_info", "u8", label="雷达信息位域", hex=True, default=0x10,
           note="bit0-1 双倍易伤机会；bit2 对方正在被触发双倍易伤；bit3-4 己方加密等级；bit5 可修改密钥")],
        note="固定 1Hz",
    ))
    add(CommandSpec(
        0x0301, "机器人交互数据", 118, "both", 30.0,
        [
            f("data_cmd_id", "u16", label="子内容 ID", default=0x0101,
              choices={0x0100: "0x0100 删除图层", 0x0101: "0x0101 绘制1个图形",
                       0x0102: "0x0102 绘制2个图形", 0x0103: "0x0103 绘制5个图形",
                       0x0104: "0x0104 绘制7个图形", 0x0110: "0x0110 绘制字符",
                       0x0120: "0x0120 哨兵自主决策指令", 0x0121: "0x0121 雷达自主决策指令"},
              note="0x0200~0x02FF 为机器人间通信，可填原始字节"),
            f("sender_id", "u16", label="发送者 ID", default=7),
            f("receiver_id", "u16", label="接收者 ID", default=0x0107,
              note="选手端 ID：0x0100+机器人ID；服务器 0x8080"),
            f("content", "bytes", size=0, label="内容数据段(≤112B)", default=b""),
        ],
        note="发送方触发，频率上限 30Hz；总帧长≤127B；UI 图形解析见接收页",
    ))
    add(CommandSpec(
        0x0302, "自定义控制器与机器人交互", 30, "down", 30.0,
        [f("data", "bytes", size=30, label="自定义数据", default=b"\x00" * 30)],
        note="图传链路；触发式，上限 30Hz",
    ))
    add(CommandSpec(
        0x0303, "选手端小地图交互数据", 12, "down", None,
        [
            f("target_position_x", "f32", label="目标 X", unit="m", default=0.0),
            f("target_position_y", "f32", label="目标 Y", unit="m", default=0.0),
            f("cmd_keyboard", "u8", label="键盘键值", hex=True, default=0),
            f("target_robot_id", "u8", label="对方机器人 ID", default=0),
            f("cmd_source", "u16", label="信息来源 ID", default=0),
        ],
        note="触发式，两次发送间隔≥0.5s（半自动控制机器人≥3s）；官方命令表长度15B与字段表12B矛盾，按字段表12B实现",
    ))
    add(CommandSpec(
        0x0305, "选手端小地图接收雷达数据", 48, "up", 5.0,
        [
            f("opponent_hero_x", "u16", label="对方英雄 X", unit="cm", default=0),
            f("opponent_hero_y", "u16", label="对方英雄 Y", unit="cm", default=0),
            f("opponent_engineer_x", "u16", label="对方工程 X", unit="cm", default=0),
            f("opponent_engineer_y", "u16", label="对方工程 Y", unit="cm", default=0),
            f("opponent_std3_x", "u16", label="对方步兵3 X", unit="cm", default=0),
            f("opponent_std3_y", "u16", label="对方步兵3 Y", unit="cm", default=0),
            f("opponent_std4_x", "u16", label="对方步兵4 X", unit="cm", default=0),
            f("opponent_std4_y", "u16", label="对方步兵4 Y", unit="cm", default=0),
            f("opponent_aerial_x", "u16", label="对方空中 X", unit="cm", default=0),
            f("opponent_aerial_y", "u16", label="对方空中 Y", unit="cm", default=0),
            f("opponent_sentry_x", "u16", label="对方哨兵 X", unit="cm", default=0),
            f("opponent_sentry_y", "u16", label="对方哨兵 Y", unit="cm", default=0),
            f("ally_hero_x", "u16", label="己方英雄 X", unit="cm", default=0),
            f("ally_hero_y", "u16", label="己方英雄 Y", unit="cm", default=0),
            f("ally_engineer_x", "u16", label="己方工程 X", unit="cm", default=0),
            f("ally_engineer_y", "u16", label="己方工程 Y", unit="cm", default=0),
            f("ally_std3_x", "u16", label="己方步兵3 X", unit="cm", default=0),
            f("ally_std3_y", "u16", label="己方步兵3 Y", unit="cm", default=0),
            f("ally_std4_x", "u16", label="己方步兵4 X", unit="cm", default=0),
            f("ally_std4_y", "u16", label="己方步兵4 Y", unit="cm", default=0),
            f("ally_aerial_x", "u16", label="己方空中 X", unit="cm", default=0),
            f("ally_aerial_y", "u16", label="己方空中 Y", unit="cm", default=0),
            f("ally_sentry_x", "u16", label="己方哨兵 X", unit="cm", default=0),
            f("ally_sentry_y", "u16", label="己方哨兵 Y", unit="cm", default=0),
        ],
        note="频率上限 5Hz；x/y 为 0 视为未发送该机器人坐标",
    ))
    add(CommandSpec(
        0x0306, "自定义控制器与选手端交互", 8, "down", 30.0,
        [
            f("key_value", "u16", label="键盘键值(两键无冲)", hex=True, default=0),
            BitGroup("mouse_x", 2, [
                bf("x_position", 0, 12, label="鼠标 X 像素", default=960),
                bf("mouse_left", 12, 4, label="鼠标左键", default=0),
            ], label="鼠标 X"),
            BitGroup("mouse_y", 2, [
                bf("y_position", 0, 12, label="鼠标 Y 像素", default=540),
                bf("mouse_right", 12, 4, label="鼠标右键", default=0),
            ], label="鼠标 Y"),
            f("reserved", "u16", label="保留位", hex=True, default=0),
        ],
        note="自定义控制器模拟键鼠；频率上限 30Hz",
    ))
    add(CommandSpec(
        0x0307, "选手端小地图路径数据", 105, "up", 1.0,
        [
            f("intention", "u8", label="意图", default=1,
              choices={1: "到目标点攻击", 2: "到目标点防守", 3: "移动到目标点"}),
            f("start_position_x", "u16", label="路径起点 X", unit="dm", default=0),
            f("start_position_y", "u16", label="路径起点 Y", unit="dm", default=0),
            f("delta_x", "bytes", size=49, label="路径点 X 增量[49]", default=b"\x00" * 49),
            f("delta_y", "bytes", size=49, label="路径点 Y 增量[49]", default=b"\x00" * 49),
            f("sender_id", "u16", label="发送者 ID", default=7),
        ],
        note="频率上限 1Hz；官方命令表长度 103B 与字段表 105B 矛盾，按字段表 105B 实现",
    ))
    add(CommandSpec(
        0x0308, "选手端小地图自定义消息", 34, "up", 3.0,
        [
            f("sender_id", "u16", label="发送者 ID", default=7),
            f("receiver_id", "u16", label="接收者 ID", default=0x0107),
            f("user_data", "bytes", size=30, label="字符(UTF-16)", default=b"\x00" * 30),
        ],
        note="频率上限 3Hz；UTF-16 编码，注意大小端",
    ))
    add(CommandSpec(
        0x0309, "自定义控制器接收机器人数据", 30, "up", 10.0,
        [f("data", "bytes", size=30, label="自定义数据", default=b"\x00" * 30)],
        note="图传链路；上限 10Hz",
    ))
    add(CommandSpec(
        0x0310, "机器人发送给自定义客户端", 300, "up", 50.0,
        [f("data", "bytes", size=300, label="自定义数据", default=b"\x00" * 300)],
        note="图传链路；上限 50Hz；无重传机制",
    ))
    add(CommandSpec(
        0x0311, "自定义客户端发送给机器人", 30, "down", 75.0,
        [f("data", "bytes", size=30, label="自定义指令", default=b"\x00" * 30)],
        note="图传链路；上限 75Hz",
    ))

    # 雷达无线链路（信号发射源→雷达；模拟器可按需投喂）
    add(CommandSpec(
        0x0A01, "对方机器人位置坐标", 24, "radar", 10.0,
        [
            f("hero_x", "u16", label="英雄 X", unit="cm"), f("hero_y", "u16", label="英雄 Y", unit="cm"),
            f("engineer_x", "u16", label="工程 X", unit="cm"), f("engineer_y", "u16", label="工程 Y", unit="cm"),
            f("std3_x", "u16", label="步兵3 X", unit="cm"), f("std3_y", "u16", label="步兵3 Y", unit="cm"),
            f("std4_x", "u16", label="步兵4 X", unit="cm"), f("std4_y", "u16", label="步兵4 Y", unit="cm"),
            f("aerial_x", "u16", label="空中 X", unit="cm"), f("aerial_y", "u16", label="空中 Y", unit="cm"),
            f("sentry_x", "u16", label="哨兵 X", unit="cm"), f("sentry_y", "u16", label="哨兵 Y", unit="cm"),
        ],
        note="10Hz 持续发送",
    ))
    add(CommandSpec(
        0x0A02, "对方机器人血量信息", 12, "radar", 10.0,
        [
            f("hero_hp", "u16", label="英雄血量", default=100),
            f("engineer_hp", "u16", label="工程血量", default=100),
            f("std3_hp", "u16", label="步兵3血量", default=100),
            f("std4_hp", "u16", label="步兵4血量", default=100),
            f("reserved", "u16", label="保留位", default=0),
            f("sentry_hp", "u16", label="哨兵血量", default=100),
        ],
        note="10Hz 持续发送",
    ))
    add(CommandSpec(
        0x0A03, "对方剩余发弹量", 10, "radar", 10.0,
        [
            f("hero_allowance", "u16", label="英雄发弹量", default=0),
            f("std3_allowance", "u16", label="步兵3发弹量", default=0),
            f("std4_allowance", "u16", label="步兵4发弹量", default=0),
            f("aerial_allowance", "u16", label="空中发弹量", default=0),
            f("sentry_allowance", "u16", label="哨兵发弹量", default=0),
        ],
        note="10Hz 持续发送",
    ))
    add(CommandSpec(
        0x0A04, "对方队伍宏观状态", 8, "radar", 10.0,
        [
            f("remaining_gold", "u16", label="剩余金币", default=0),
            f("total_gold", "u16", label="累计总金币", default=0),
            f("macro_status", "u32", label="宏观状态位域", hex=True, default=0),
        ],
        note="10Hz 持续发送",
    ))
    add(CommandSpec(
        0x0A05, "对方各机器人增益效果", 41, "radar", 10.0,
        [
            f("hero_recovery", "u8", label="英雄回血增益", unit="%"),
            f("hero_cooling", "u16", label="英雄冷却增益", unit="/s"),
            f("hero_defence", "u8", label="英雄防御增益", unit="%"),
            f("hero_vulnerability", "u8", label="英雄负防御增益", unit="%"),
            f("hero_attack", "u16", label="英雄攻击增益", unit="%"),
            f("engineer_recovery", "u8", label="工程回血增益", unit="%"),
            f("engineer_cooling", "u16", label="工程冷却增益", unit="/s"),
            f("engineer_defence", "u8", label="工程防御增益", unit="%"),
            f("engineer_vulnerability", "u8", label="工程负防御增益", unit="%"),
            f("engineer_attack", "u16", label="工程攻击增益", unit="%"),
            f("std3_recovery", "u8", label="步兵3回血增益", unit="%"),
            f("std3_cooling", "u16", label="步兵3冷却增益", unit="/s"),
            f("std3_defence", "u8", label="步兵3防御增益", unit="%"),
            f("std3_vulnerability", "u8", label="步兵3负防御增益", unit="%"),
            f("std3_attack", "u16", label="步兵3攻击增益", unit="%"),
            f("std4_recovery", "u8", label="步兵4回血增益", unit="%"),
            f("std4_cooling", "u16", label="步兵4冷却增益", unit="/s"),
            f("std4_defence", "u8", label="步兵4防御增益", unit="%"),
            f("std4_vulnerability", "u8", label="步兵4负防御增益", unit="%"),
            f("std4_attack", "u16", label="步兵4攻击增益", unit="%"),
            f("sentry_recovery", "u8", label="哨兵回血增益", unit="%"),
            f("sentry_cooling", "u16", label="哨兵冷却增益", unit="/s"),
            f("sentry_defence", "u8", label="哨兵防御增益", unit="%"),
            f("sentry_vulnerability", "u8", label="哨兵负防御增益", unit="%"),
            f("sentry_attack", "u16", label="哨兵攻击增益", unit="%"),
            f("sentry_posture", "u8", label="哨兵姿态",
              choices={1: "进攻", 2: "防御", 3: "移动", 4: "强化进攻", 5: "强化防御", 6: "强化移动"}),
            f("hero_status", "u8", label="英雄状态",
              choices={0: "存活", 1: "战亡", 2: "无敌不虚弱", 3: "无敌且虚弱"}),
            f("engineer_status", "u8", label="工程状态",
              choices={0: "存活", 1: "战亡", 2: "无敌不虚弱", 3: "无敌且虚弱"}),
            f("std3_status", "u8", label="步兵3状态",
              choices={0: "存活", 1: "战亡", 2: "无敌不虚弱", 3: "无敌且虚弱"}),
            f("std4_status", "u8", label="步兵4状态",
              choices={0: "存活", 1: "战亡", 2: "无敌不虚弱", 3: "无敌且虚弱"}),
            f("sentry_status", "u8", label="哨兵状态",
              choices={0: "存活", 1: "战亡", 2: "无敌不虚弱", 3: "无敌且虚弱"}),
        ],
        note="10Hz 持续发送",
    ))
    add(CommandSpec(
        0x0A06, "对方干扰波密钥", 6, "radar", 10.0,
        [f("password", "bytes", size=6, label="密钥(ASCII字母/数字)", default=b"ABCDEF")],
        note="10Hz 持续发送",
    ))
    return cmds


COMMANDS: dict[int, CommandSpec] = _commands()


def encode_command(spec: CommandSpec, values: dict[str, object] | None = None,
                   content: bytes | None = None) -> bytes:
    """按命令定义编码数据段。content 供 0x0301 等动态内容字段使用。"""
    values = values or {}
    out = bytearray()
    dynamic_provided = False
    for chunk in spec.chunks:
        if isinstance(chunk, BitGroup):
            v = 0
            for bit in chunk.bits:
                raw = values.get(bit.name, bit.default)
                bv = int(raw) if raw is not None else 0
                bv &= (1 << bit.width) - 1
                v |= bv << bit.lsb
            out += v.to_bytes(chunk.size, "little")
        elif chunk.ctype == "bytes":
            raw = values.get(chunk.name, chunk.default)
            if chunk.name == "content" and content is not None:
                raw = content
            if chunk.size == 0 and chunk.name == "content":
                dynamic_provided = "content" in values or content is not None
            data = raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
            if chunk.size:
                data = (bytes(data) + b"\x00" * chunk.size)[:chunk.size]
            out += data
        else:
            raw = values.get(chunk.name, chunk.default)
            out += struct.pack(FORMATS[chunk.ctype], raw)
    # 动态长度字段（如 0x0301 content）：未提供内容时按官方最大长度补零
    if not dynamic_provided and len(out) < spec.length and spec.chunks \
            and isinstance(spec.chunks[-1], Field) \
            and spec.chunks[-1].ctype == "bytes" and spec.chunks[-1].size == 0:
        out += b"\x00" * (spec.length - len(out))
    return bytes(out)


def decode_command(spec: CommandSpec, data: bytes) -> dict[str, object]:
    """按命令定义解码数据段；数据不足时补零并标记 _truncated。"""
    values: dict[str, object] = {}
    off = 0
    needed = spec.minimal_length
    if len(data) < needed:
        values["_truncated"] = True
        data = data + b"\x00" * (needed - len(data))
    for chunk in spec.chunks:
        if isinstance(chunk, BitGroup):
            v = int.from_bytes(data[off: off + chunk.size], "little")
            for bit in chunk.bits:
                values[bit.name] = (v >> bit.lsb) & ((1 << bit.width) - 1)
            off += chunk.size
        elif chunk.ctype == "bytes":
            size = chunk.size or (len(data) - off)
            values[chunk.name] = data[off: off + size]
            off += size
        else:
            values[chunk.name] = struct.unpack_from(FORMATS[chunk.ctype], data, off)[0]
            off += struct.calcsize(FORMATS[chunk.ctype])
    return values


def default_values(spec: CommandSpec) -> dict[str, object]:
    values: dict[str, object] = {}
    for chunk in spec.chunks:
        if isinstance(chunk, BitGroup):
            for bit in chunk.bits:
                values[bit.name] = bit.default
        elif chunk.ctype == "bytes":
            values[chunk.name] = chunk.default
        else:
            values[chunk.name] = chunk.default
    return values
