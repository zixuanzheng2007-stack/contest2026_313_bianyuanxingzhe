"""Three-demo analysis must require every software stage and stay honest."""
import unittest

from stage3_demo_acceptance import analyze_transcript


def transcript(run_count=1, omit="", fatal=False):
    chunks = []
    for index in range(1, run_count + 1):
        chunks.extend((
            f"=== STAGE3 RUN {index}/{run_count} ===",
            "[ew-ctl] goto warn",
            "[ew-ctl] fake 1.0m 40.0km/h -> EMERGENCY",
        ))
        for stage in ("decision", "agent", "tool", "alert_output", "complete"):
            if stage != omit:
                chunks.append(f"[ew_event] event_id={index} stage={stage}")
        chunks.extend((
            "[alert_output] level=EMERGENCY reason=approach",
            "[ew-ctl] goto chat",
            "[ew-ctl] goto wifi",
            "[ew-ctl] goto warn",
            f'[ew-snapshot] {{"v":1,"id":"stage3-{index}"}}',
        ))
    if fatal:
        chunks.append("HardFault")
    return "\n".join(chunks)


class Stage3DemoTests(unittest.TestCase):
    def test_three_complete_chains_pass_software_only(self):
        result = analyze_transcript(transcript(3), 3)
        self.assertEqual(result["software_chain"], "PASS")
        self.assertEqual(result["complete_event_chains"], 3)
        self.assertEqual(result["physical_screen_buzzer_radar"], "PENDING")
        self.assertFalse(result["board_tested"])

    def test_missing_stage_or_fatal_marker_fails(self):
        self.assertEqual(analyze_transcript(transcript(3, omit="tool"), 3)["software_chain"], "FAIL")
        self.assertEqual(analyze_transcript(transcript(3, fatal=True), 3)["software_chain"], "FAIL")

    def test_wrong_run_count_fails(self):
        self.assertEqual(analyze_transcript(transcript(2), 3)["software_chain"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
