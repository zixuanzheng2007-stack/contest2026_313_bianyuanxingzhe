from edge_walker.models import RadarTarget
from edge_walker.protocol import (
    FrameStreamParser,
    build_detect_frame,
    parse_detect_frame,
)
from edge_walker.policy import ApproachPolicy, PolicyConfig, compute_ttc_s
from edge_walker.agent_bridge import AgentBridge
from edge_walker.simulator import ApproachScenario, receding_noise, slow_target


def test_roundtrip_frame():
    t = RadarTarget(range_m=18, speed_kmh=30, approaching=True, azimuth_deg=-5, snr=22, alarm=True)
    raw = build_detect_frame([t])
    frame = parse_detect_frame(raw)
    assert len(frame.targets) == 1
    got = frame.targets[0]
    assert got.range_m == 18
    assert got.speed_kmh == 30
    assert got.approaching is True
    assert got.azimuth_deg == -5
    assert got.snr == 22


def test_stream_parser_handles_chunked_bytes():
    t = RadarTarget(range_m=12, speed_kmh=20, approaching=True, snr=10, alarm=True)
    raw = build_detect_frame([t])
    parser = FrameStreamParser()
    assert parser.feed(raw[:3]) == []
    frames = parser.feed(raw[3:])
    assert len(frames) == 1
    assert frames[0].targets[0].range_m == 12


def test_filter_rejects_receding_and_slow():
    policy = ApproachPolicy()
    level, event = policy.evaluate([receding_noise()])
    assert level.value == "NONE" and event is None
    level, event = policy.evaluate([slow_target()])
    assert level.value == "NONE" and event is None


def test_ttc_and_levels_escalate():
    cfg = PolicyConfig()
    policy = ApproachPolicy(cfg)
    # 40m @ 25km/h → soft by range/ttc band around soft
    far = RadarTarget(range_m=30, speed_kmh=25, approaching=True, snr=20, alarm=True)
    level, event = policy.evaluate([far])
    assert event is not None
    assert level.value in {"SOFT", "STRONG", "EMERGENCY"}
    assert compute_ttc_s(far) is not None

    near = RadarTarget(range_m=6, speed_kmh=30, approaching=True, snr=25, alarm=True)
    level, event = policy.evaluate([near])
    assert level.value == "EMERGENCY"
    assert event.event == "approach_threshold_exceeded"


def test_agent_proactive_tool():
    policy = ApproachPolicy()
    agent = AgentBridge()
    scenario = ApproachScenario(start_range_m=20, end_range_m=10, step_m=5, speed_kmh=30)
    calls = 0
    for t in scenario.targets_over_time():
        level, event = policy.evaluate([t])
        if event:
            agent.ingest(event)
            calls += 1
    assert calls >= 1
    assert len(agent.tool_calls) == calls
    assert agent.tool_calls[0].name == "haptic_alert"
