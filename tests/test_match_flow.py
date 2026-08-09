from referee_sim_app.core.match_flow import MatchConfig, MatchFlow
from referee_sim_app.protocol.commands import COMMANDS, default_values, encode_command


def make_flow(**kw) -> MatchFlow:
    defaults = dict(
        idle_duration=0.2,
        prep_duration=0.3,
        selfcheck_duration=0.2,
        countdown_duration=0.2,
        match_duration=1.0,
        settlement_duration=0.2,
        shoot_interval=0.1,
        hurt_interval=0.25,
        warning_after=0.3,
    )
    defaults.update(kw)
    cfg = MatchConfig(**defaults)
    return MatchFlow(cfg)


def _run_to(f: MatchFlow, phase: int, dt: float = 0.05, limit: float = 10.0):
    t = 0.0
    while f.phase < phase and t < limit:
        f.update(dt)
        t += dt


def test_phase_transitions():
    f = make_flow()
    phases = []
    t = 0.0
    while f.phase < 6 and t < 10:
        for ev in f.update(0.05):
            if ev["type"] == "phase":
                phases.append(ev["phase"])
        t += 0.05
    assert phases == [1, 2, 3, 4, 5, 6]


def test_match_events():
    f = make_flow()
    _run_to(f, 4)
    events = []
    for _ in range(20):
        events += f.update(0.05)
    kinds = {e["type"] for e in events}
    assert "shoot" in kinds
    assert "hurt" in kinds
    assert "warning" in kinds


def test_hp_decreases_during_match():
    f = make_flow()
    _run_to(f, 4)
    hp0 = f.values()["current_hp"]
    for _ in range(10):
        f.update(0.1)
    hp1 = f.values()["current_hp"]
    assert hp1 < hp0
    assert hp1 >= 15


def test_heat_accumulates_and_stays_in_range():
    f = make_flow(match_duration=5.0)
    _run_to(f, 4)
    for _ in range(50):
        f.update(0.1)
    heat = f.values()["shooter_17mm_barrel_heat"]
    assert heat > 0
    assert 0 <= heat <= f.config.heat_limit


def test_result_event_has_winner():
    f = make_flow()
    result = None
    t = 0.0
    while f.phase < 6 and t < 10:
        for ev in f.update(0.05):
            if ev["type"] == "result":
                result = ev
        t += 0.05
    assert result is not None
    assert result["winner"] in (1, 2)


def test_values_snapshot_covers_periodic_commands():
    f = make_flow()
    _run_to(f, 4)
    f.update(0.1)
    v = f.values()
    periodic = [0x0001, 0x0003, 0x0101, 0x0104, 0x0105,
                0x0201, 0x0202, 0x0203, 0x0204, 0x0208, 0x0209, 0x020A,
                0x020B, 0x020C, 0x020D, 0x020E]
    for cmd_id in periodic:
        spec = COMMANDS[cmd_id]
        values = default_values(spec)
        values.update(v)
        data = encode_command(spec, values)
        assert len(data) == spec.length, f"0x{cmd_id:04X} 长度错误"
