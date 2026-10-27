"""Three-demo analysis must require every software stage and stay honest."""
import unittest
import json
from test_mobile_serial_gateway import board_snapshot

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
                chunks.append(f"[ew_event] event_id={index} stage={stage}" + (" result=0" if stage == "complete" else ""))
        chunks.extend((
            "[alert_output] level=EMERGENCY reason=approach",
            "[ew-ctl] goto chat",
            "[ew-ctl] goto wifi",
            "[ew-ctl] goto warn",
            '[ew-snapshot] '+json.dumps(board_snapshot("stage3-"+str(index),index)),
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

    def test_failed_completion_is_not_success(self):
        text = transcript(3).replace('stage=complete result=0','stage=complete result=-16')
        self.assertEqual(analyze_transcript(text,3)['software_chain'],'FAIL')

    def test_empty_later_runs_are_not_covered_by_first_run(self):
        text = transcript(3).replace('=== STAGE3 RUN 2/3 ===','').replace('=== STAGE3 RUN 3/3 ===','')
        text += '\n=== STAGE3 RUN 2/3 ===\n=== STAGE3 RUN 3/3 ===\n'
        self.assertEqual(analyze_transcript(text,3)['software_chain'],'FAIL')

    def test_replayed_snapshot_is_rejected(self):
        text = transcript(3).replace('"snapshot_seq": 2','"snapshot_seq": 1')
        self.assertEqual(analyze_transcript(text,3)['software_chain'],'FAIL')

    def test_optional_actuator_stage_preserves_dispatch_evidence(self):
        text = transcript(3).replace('stage=complete result=0','stage=actuator actuator=lcd\n[ew_event] event_id=99999 stage=complete result=0')
        # A completion with an unrelated ID must not complete the dispatch chain.
        self.assertEqual(analyze_transcript(text,3)['software_chain'],'FAIL')


if __name__ == "__main__":
    unittest.main(verbosity=2)
