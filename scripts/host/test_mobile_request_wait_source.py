from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "mobile/android/src/com/edgewalker/companion/MainActivity.java").read_text(encoding="utf-8")


def body(signature):
    start = MAIN.index("{", MAIN.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (MAIN[end] == "{") - (MAIN[end] == "}")
        end += 1
    return MAIN[start + 1:end - 1]


class RequestWaitSourceTest(unittest.TestCase):
    def test_receive_expires_before_ack_or_result_processing(self):
        receive = body("private void receive(")
        guard = receive.index("expirePendingRequests(receivedAt);")
        lookup = receive.index("Pending item = pending.get(id);")
        unknown = receive.index("if (item == null)")
        queued = receive.index("item.waitState.markQueued(receivedAt)")
        applied = receive.index("applyResult(item.operation, data);")
        self.assertLess(receive.index("receivedAt = SystemClock.elapsedRealtime()"), guard)
        self.assertLess(guard, lookup)
        self.assertLess(lookup, unknown)
        self.assertLess(unknown, queued)
        self.assertLess(queued, applied)
        self.assertIn("return;", body("if (item == null)"))
        self.assertNotIn("applyResult", body("if (item == null)"))
        self.assertNotIn("markQueued", body("if (item == null)"))
        self.assertNotIn("client.send", receive)
        self.assertNotIn("request(", receive)

    def test_shared_expiry_removes_updates_controls_and_disconnects_hello(self):
        expiry = body("private void expirePendingRequests(")
        self.assertIn("item.waitState.isExpired(now)", expiry)
        self.assertIn("iterator.remove();", expiry)
        self.assertIn('helloTimedOut |= "hello".equals(item.operation);', expiry)
        self.assertIn("disconnect(", expiry)
        self.assertIn("updateControls();", expiry)
        self.assertIn("item.waitState.isQueued()", expiry)
        self.assertNotIn("request(", expiry)
        self.assertNotIn("client.send", expiry)
        watchdog = body("private final Runnable watchdog")
        self.assertIn("expirePendingRequests(now);", watchdog)
        self.assertNotIn("iterator.remove", watchdog)
        self.assertNotIn("request(", watchdog)
        self.assertNotIn("client.send", watchdog)
        self.assertNotIn("item.deadline =", MAIN)

    def test_duplicate_queued_ui_is_inside_first_transition_guard(self):
        transition = body("if (item.waitState.markQueued(receivedAt))")
        self.assertIn("showAction(", transition)
        self.assertIn("appendLog(", transition)
        self.assertNotIn("updateControls", transition)

    def test_timeout_retains_unknown_outcome_and_stale_ignore(self):
        # Escape literals keep this test independent of the shell's encoding.
        self.assertIn("\u7b49\u5f85\u8d85\u65f6\uff0c\u6267\u884c\u7ed3\u679c\u672a\u77e5\uff0c\u8bf7\u5237\u65b0\u786e\u8ba4", MAIN)
        self.assertIn("\u5df2\u6392\u961f\u4f46\u65e0\u6700\u7ec8\u56de\u590d", MAIN)
        self.assertIn("\u5ffd\u7565\u8fc7\u671f\u6216\u672a\u77e5\u8bf7\u6c42\u7684\u56de\u590d", MAIN)


if __name__ == "__main__":
    unittest.main()
