"""Exercise the real IPC Tool, single-slot transport, and LCD consumer body."""
from __future__ import annotations

import json
import errno
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/edge_walker"


def main() -> None:
    lcd = (SOURCE / "alert_lcd.c").read_text(encoding="utf-8")
    anchor = re.search(r"static (?:int|void) queue_request\(", lcd)
    assert anchor is not None, "LCD queue_request implementation missing"
    consumer = lcd[anchor.start():lcd.index(
        "/****************************************************************************\n * 雷达")]
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int fault, interrupted, writing_ack;
static void consume_during_write(void);
static ssize_t test_write(int fd, const void *buf, size_t size) {
  if (fault == 6 && writing_ack) { errno = EIO; return -1; }
  if (fault == 1) return write(fd, buf, size / 2);
  if (fault == 2) { errno = EIO; return -1; }
  if (fault == 3 && !interrupted++) { errno = EINTR; return -1; }
  if (fault == 5) { consume_during_write(); errno = EIO; return -1; }
  return write(fd, buf, size);
}
static int test_open(const char *path, int flags, ...) {
  int mode = 0;
  if (fault == 4) { errno = EACCES; return -1; }
  if (flags & O_WRONLY) writing_ack = strstr(path, "/ack.tmp") != NULL;
  if (flags & O_CREAT) {
    va_list args; va_start(args, flags); mode = va_arg(args, int); va_end(args);
    return open(path, flags, mode);
  }
  return open(path, flags);
}
static int test_unlink(const char *path) {
  if (fault == 8 && strstr(path, "/processing")) { errno = EIO; return -1; }
  if (fault == 10 && strstr(path, ".result")) { errno = EIO; return -1; }
  return unlink(path);
}
#define EW_ALERT_IPC_WRITE test_write
#define EW_ALERT_IPC_OPEN test_open
#define EW_ALERT_IPC_UNLINK test_unlink
#include "ai_agent_ext/ew_alert_ipc.h"
#include "ai_agent_ext/tool_approach_alert_ipc.c"
#include "alert_output.h"
#include "ew_safety.h"
#define EW_REQ_POLL_MS 200u
static uint32_t g_last_req_ms;
static int g_ui_ready = 1;
static void *g_scr = (void *)1, *g_label = (void *)1;
static int buzz_calls, ui_calls;
static ew_alert_level_t safety_floor, g_external_level;
static char g_external_reason[96];
static bool g_external_active;
void ew_safety_snapshot(ew_safety_snapshot_t *out) {
  memset(out, 0, sizeof(*out));
  out->decision.level = safety_floor;
}
const char *ew_alert_level_name(ew_alert_level_t level) {
  return level_name((int)level);
}
static void alert_buzzer_level(ew_alert_level_t level) {
  assert(level >= 0 && level <= 3);
  buzz_calls++; printf("ACT_BUZZER %d\n", (int)level);
}
static void apply_alert_ui(ew_alert_level_t level, const char *reason) {
  char escaped[EW_ALERT_REASON_SIZE * 6];
  ew_alert_request_t contender = {0};
  assert(ew_alert_ipc_publish(&contender) == -EBUSY);
  assert(access(EW_ALERT_ACK, F_OK) != 0);
  assert(ew_alert_json_escape(reason, escaped, sizeof(escaped)) == 0);
  ui_calls++; printf("ACT_UI %d \"%s\"\n", (int)level, escaped);
  if (fault == 9) {
    FILE *ready = fopen("consumer.ready", "w");
    assert(ready != NULL); fclose(ready);
    assert(getchar() == 'x');
  }
}
''' + consumer + r'''
static void consume_during_write(void) {
  assert(access(EW_ALERT_MUTEX, F_OK) == 0);
  poll_request(EW_REQ_POLL_MS);
  assert(buzz_calls == 0 && ui_calls == 0);
  assert(access(EW_ALERT_CONSUMER, F_OK) != 0);
  assert(access(EW_ALERT_SLOT, F_OK) == 0);
}
int main(int argc, char **argv) {
  char output[256];
  int ret;
  assert(argc >= 2);
  if (!strcmp(argv[1], "writer")) {
    assert(argc >= 3);
    if (argc > 3) fault = atoi(argv[3]);
    ret = tool_approach_alert_execute(!strcmp(argv[2], "--null") ? NULL : argv[2],
                                    output, sizeof(output));
    printf("REPLY %s\n", output);
    return ret < 0 ? 3 : 0;
  }
  if (!strcmp(argv[1], "consume")) {
    if (argc > 2) fault = atoi(argv[2]);
    if (argc > 3) safety_floor = (ew_alert_level_t)atoi(argv[3]);
    poll_request(EW_REQ_POLL_MS);
    assert(buzz_calls == ui_calls);
    if (ui_calls) {
      assert(g_external_level >= safety_floor);
      assert(g_external_active == (g_external_level != EW_ALERT_NONE));
    }
    printf("EXTERNAL_ACTIVE %d\n", (int)g_external_active);
    printf("CALLS %d\n", ui_calls);
    return 0;
  }
  if (!strcmp(argv[1], "consume_retry")) {
    assert(argc > 2); fault = atoi(argv[2]);
    poll_request(EW_REQ_POLL_MS);
    assert(ui_calls == 1 && buzz_calls == 1);
    fault = 0;
    poll_request(EW_REQ_POLL_MS * 2);
    assert(ui_calls == 1 && buzz_calls == 1);
    assert(access(EW_ALERT_RESULT, F_OK) != 0);
    assert(access(EW_ALERT_SLOT, F_OK) != 0);
    assert(access(EW_ALERT_MUTEX, F_OK) != 0);
    assert(access(EW_ALERT_ACK, F_OK) == 0);
    printf("RETRY_CALLS %d\n", ui_calls);
    return 0;
  }
  if (!strcmp(argv[1], "consume_rejoin")) {
    FILE *ready;
    fault = 6;
    poll_request(EW_REQ_POLL_MS);
    assert(ui_calls == 1);
    ready = fopen("consumer.ready", "w");
    assert(ready != NULL); fclose(ready);
    assert(getchar() == 'x');
    fault = 0;
    poll_request(EW_REQ_POLL_MS * 2);
    assert(ui_calls == 2 && buzz_calls == 2);
    printf("REJOIN_CALLS %d\n", ui_calls);
    return 0;
  }
  if (!strcmp(argv[1], "legacy")) {
    queue_request(EW_ALERT_STRONG, "legacy", 87);
    return 0;
  }
  return 4;
}
'''
    with tempfile.TemporaryDirectory(prefix="ew_alert_ipc_") as directory:
        path = Path(directory)
        cfile, exe = path / "ipc.c", path / "ipc.exe"
        cfile.write_text(harness, encoding="utf-8")
        subprocess.run([
            "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
            '-DEW_ALERT_REQ="request"', "-I", str(SOURCE),
            str(cfile), "-o", str(exe),
        ], check=True)

        def run(work: Path, *args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(exe), *args], cwd=work,
                                  capture_output=True, text=True, encoding="utf-8", timeout=10)

        def workspace(name: str) -> Path:
            work = path / name
            work.mkdir()
            return work

        def reply(result: subprocess.CompletedProcess[str]) -> dict:
            return json.loads(next(line[6:] for line in result.stdout.splitlines()
                                   if line.startswith("REPLY ")))

        # Further cases below deliberately use independent processes and files.
        work = workspace("ten_events")
        for event_id in range(1, 11):
            reason = 'R 12m "approaching"\n' + "侧后"
            result = run(work, "writer", json.dumps({
                "level": event_id % 4, "event_id": event_id, "reason": reason,
            }))
            assert result.returncode == 0, result.stdout + result.stderr
            assert reply(result)["status"] == "queued", result.stdout
            assert "applied" not in result.stdout and "[alert_output]" not in result.stdout
            assert not (work / "request.ack").exists()
            consumed = run(work, "consume")
            assert consumed.returncode == 0, consumed.stderr
            out = consumed.stdout
            assert f"event_id={event_id} stage=applied" in out, out
            assert out.index("ACT_BUZZER") < out.index("ACT_UI") < out.index("stage=applied") < out.index("stage=ack"), out
            actual_reason = json.loads(next(line.split(" ", 2)[2]
                                           for line in out.splitlines()
                                           if line.startswith("ACT_UI ")))
            assert actual_reason == reason, out
            assert (work / "request.ack").read_text() == f"EWA1 {event_id} applied 0\n"
            assert not (work / "request.lock").exists()
            assert "CALLS 0" in run(work, "consume").stdout

        work = workspace("busy")
        assert run(work, "writer", '{"level":"strong","event_id":21}').returncode == 0
        before = (work / "request").read_bytes()
        rejected = run(work, "writer", '{"level":"none","event_id":22}')
        assert rejected.returncode != 0 and reply(rejected)["error"] == "busy", rejected.stdout
        assert before == (work / "request").read_bytes()
        assert "event_id=21 stage=applied" in run(work, "consume").stdout

        work = workspace("concurrent_publishers")
        publishers = [subprocess.Popen([
            str(exe), "writer", json.dumps({"level": 2, "event_id": event}),
        ], cwd=work, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8") for event in (41, 42)]
        published = [process.communicate(timeout=10) for process in publishers]
        assert sorted(process.returncode for process in publishers) == [0, 3], published
        winner = 41 if publishers[0].returncode == 0 else 42
        assert f"event_id={winner} stage=applied" in run(work, "consume").stdout

        work = workspace("orphan_request")
        (work / "request").write_bytes(b"old request")
        assert reply(run(work, "writer", '{"level":0}'))["error"] == "busy"
        assert (work / "request").read_bytes() == b"old request"
        assert not (work / "request.lock").exists()

        work = workspace("unknown_mutex")
        assert run(work, "writer", '{"level":2,"event_id":35}').returncode == 0
        before = (work / "request").read_bytes()
        (work / "request.mutex").mkdir()
        assert "CALLS 0" in run(work, "consume").stdout
        assert (work / "request.mutex").exists()
        assert (work / "request").read_bytes() == before

        work = workspace("malformed_result")
        assert run(work, "writer", '{"level":2,"event_id":36}').returncode == 0
        (work / "request.lock/consumer").mkdir()
        (work / "request").rename(work / "request.lock/processing")
        (work / "request.result").write_text("EWR1 36 invalid\n")
        assert "CALLS 0" in run(work, "consume").stdout
        assert (work / "request.lock/processing").exists()
        assert (work / "request.result").read_text() == "EWR1 36 invalid\n"

        work = workspace("concurrent_ack_recovery")
        assert run(work, "writer", '{"level":2,"event_id":37}').returncode == 0
        assert "CALLS 1" in run(work, "consume", "6").stdout
        consumers = [subprocess.Popen([str(exe), "consume"], cwd=work,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8") for _ in range(2)]
        recovered_outputs = [process.communicate(timeout=10) for process in consumers]
        assert all(process.returncode == 0 for process in consumers), recovered_outputs
        assert all("CALLS 0" in output for output, _ in recovered_outputs), recovered_outputs
        assert sum(output.count("event_id=37 stage=ack result=0")
                   for output, _ in recovered_outputs) == 1, recovered_outputs
        assert not (work / "request.result").exists()
        assert not (work / "request.lock").exists()
        # A second consumer cannot claim a request already being processed.
        work = workspace("claimed")
        assert run(work, "writer", '{"level":2,"event_id":23}').returncode == 0
        (work / "request.lock/consumer").mkdir()
        (work / "request").rename(work / "request.lock/processing")
        assert "CALLS 0" in run(work, "consume").stdout
        assert reply(run(work, "writer", '{"level":0}'))["error"] == "busy"

        # A consumer seeing a publisher between mkdir and rename must not unlock it.
        work = workspace("publishing")
        (work / "request.lock").mkdir()
        assert "CALLS 0" in run(work, "consume").stdout
        assert (work / "request.lock").is_dir()
        assert not (work / "request.lock/consumer").exists()

        invalid = ["--null", "", "{}", '{"reason":"only"}',
                   '{"level":"bad"}', '{"level":null}', '{"level":-1}',
                   '{"level":4}', '{"level":1.5}', '{"level":01}',
                   '{"level":"none",}', '{"level":"none"} trailing',
                   '{"level":0,"level":3}', '{"level":1,"extra":1}',
                   '{"level":1,"event_id":-1}', '{"level":1,"event_id":1e3}',
                   '{"level":1,"reason":"\\u0000"}',
                   '{"level":1,"reason":"\\ud800"}',
                   json.dumps({"level": 1, "reason": "x" * 96})]
        work = workspace("invalid")
        for value in invalid:
            rejected = run(work, "writer", value)
            assert rejected.returncode != 0 and reply(rejected)["ok"] is False, (value, rejected.stdout)
            assert not (work / "request").exists()
            assert not (work / "request.lock").exists()

        # Faults exercise the actual producer with open, short write and I/O errors.
        for fault in (1, 2, 4, 5):
            work = workspace(f"writer_fault_{fault}")
            rejected = run(work, "writer", '{"level":2}', str(fault))
            assert rejected.returncode != 0 and reply(rejected)["error"] == "queue_failed", rejected.stdout
            assert not (work / "request").exists()
            assert not (work / "request.lock").exists()
            assert not (work / "request.mutex").exists()
            assert run(work, "writer", '{"level":2}').returncode == 0
            assert "CALLS 1" in run(work, "consume").stdout
        work = workspace("eintr")
        assert run(work, "writer", '{"level":1}', "3").returncode == 0
        assert "CALLS 1" in run(work, "consume", "3").stdout

        # In-process retries retain an apply result even when storage cannot
        # yet record it. ACK and cleanup retries must never replay the callback.
        for fault in (1, 2, 6, 8, 10):
            work = workspace(f"live_retry_{fault}")
            assert run(work, "writer", '{"level":2,"event_id":31}').returncode == 0
            recovered = run(work, "consume_retry", str(fault))
            assert recovered.returncode == 0, recovered.stdout + recovered.stderr
            assert "RETRY_CALLS 1" in recovered.stdout
            assert (work / "request.ack").read_text() == "EWA1 31 applied 0\n"
            assert run(work, "writer", '{"level":0,"event_id":32}').returncode == 0
            assert "CALLS 1" in run(work, "consume").stdout

        # A persisted result permits another process to finish ACK/cleanup.
        for fault in (6, 8, 10):
            work = workspace(f"recorded_retry_{fault}")
            assert run(work, "writer", '{"level":2,"event_id":33}').returncode == 0
            failed_ack = run(work, "consume", str(fault))
            assert failed_ack.returncode == 0, failed_ack.stdout + failed_ack.stderr
            assert "CALLS 1" in failed_ack.stdout and "stage=ack_failed" in failed_ack.stdout
            assert (work / "request.result").read_text() == "EWR1 33 0\n"
            assert not (work / "request.mutex").exists()
            assert reply(run(work, "writer", '{"level":0}'))["error"] == "busy"
            recovered = run(work, "consume")
            assert recovered.returncode == 0 and "CALLS 0" in recovered.stdout, recovered.stdout
            assert "event_id=33 stage=ack result=0" in recovered.stdout, recovered.stdout
            assert (work / "request.ack").read_text() == "EWA1 33 applied 0\n"
            assert not (work / "request.result").exists()
            assert not (work / "request.lock").exists()
            assert "CALLS 0" in run(work, "consume").stdout
            assert run(work, "writer", '{"level":0}').returncode == 0
            assert "CALLS 1" in run(work, "consume").stdout

        # The real callback must refuse external levels below the live radar
        # floor before touching either actuator, while still ACKing rejection.
        for level in (0, 1, 2, 3):
            work = workspace(f"safety_floor_{level}")
            assert run(work, "writer", json.dumps({"level": level, "event_id": 70 + level})).returncode == 0
            consumed = run(work, "consume", "0", "3")
            assert consumed.returncode == 0, consumed.stdout + consumed.stderr
            count = 1 if level == 3 else 0
            assert f"CALLS {count}" in consumed.stdout, consumed.stdout
            status, code = ("applied", 0) if count else ("rejected", -errno.EPERM)
            assert (work / "request.ack").read_text() == f"EWA1 {70 + level} {status} {code}\n"
            assert not (work / "request.lock").exists()

        # Replaying finalization cannot turn an earlier safety rejection into
        # an apply just because the radar floor has fallen in the meantime.
        work = workspace("rejected_ack_recovery")
        assert run(work, "writer", '{"level":1,"event_id":74}').returncode == 0
        assert "CALLS 0" in run(work, "consume", "6", "3").stdout
        assert "CALLS 0" in run(work, "consume", "0", "0").stdout
        assert (work / "request.ack").read_text() == f"EWA1 74 rejected {-errno.EPERM}\n"

        work = workspace("manual_clear_active")
        assert run(work, "writer", '{"level":0,"event_id":75}').returncode == 0
        cleared = run(work, "consume")
        assert cleared.returncode == 0 and "CALLS 1" in cleared.stdout, cleared.stdout
        assert "EXTERNAL_ACTIVE 0" in cleared.stdout, cleared.stdout
        assert (work / "request.ack").read_text() == "EWA1 75 applied 0\n"

        # Without any persisted result, a replacement process cannot know
        # whether hardware ran. Unknown ownership stays fail-closed.
        work = workspace("unrecorded_crash")
        assert run(work, "writer", '{"level":2,"event_id":34}').returncode == 0
        failed_record = run(work, "consume", "2")
        assert "CALLS 1" in failed_record.stdout, failed_record.stdout
        assert not (work / "request.result").exists()
        assert (work / "request.lock/processing").exists()
        assert "CALLS 0" in run(work, "consume").stdout
        assert reply(run(work, "writer", '{"level":0}'))["error"] == "busy"

        def wait_ready(work: Path, process: subprocess.Popen[str]) -> None:
            deadline = time.monotonic() + 5
            while not (work / "consumer.ready").exists():
                assert process.poll() is None, process.communicate(timeout=1)
                assert time.monotonic() < deadline, "consumer did not reach rendezvous"
                time.sleep(0.01)

        # Hold the actual callback while another consumer and publisher race.
        work = workspace("consumer_publisher_race")
        assert run(work, "writer", '{"level":2,"event_id":51}').returncode == 0
        active = subprocess.Popen([str(exe), "consume", "9"], cwd=work,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8")
        wait_ready(work, active)
        assert reply(run(work, "writer", '{"level":0}'))["error"] == "busy"
        assert "CALLS 0" in run(work, "consume").stdout
        output, error = active.communicate("x\n", timeout=10)
        assert active.returncode == 0 and "CALLS 1" in output, output + error
        assert "CALLS 0" in run(work, "consume").stdout

        # Cross-process recovery can finish a live owner's durable result.
        # Its stale local pending state must not delete or complete a new event.
        work = workspace("live_owner_rejoin")
        assert run(work, "writer", '{"level":2,"event_id":61}').returncode == 0
        active = subprocess.Popen([str(exe), "consume_rejoin"], cwd=work,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8")
        wait_ready(work, active)
        assert "CALLS 0" in run(work, "consume").stdout
        assert (work / "request.ack").read_text() == "EWA1 61 applied 0\n"
        assert run(work, "writer", '{"level":1,"event_id":62}').returncode == 0
        output, error = active.communicate("x\n", timeout=10)
        assert active.returncode == 0 and "REJOIN_CALLS 2" in output, output + error
        assert (work / "request.ack").read_text() == "EWA1 62 applied 0\n"

        for index, damaged in enumerate((b"", b"EWA1 1 9 61\n", b"EWA1 2 1 00\n",
                                         b"EWA1 2 1 61", b"EWA1 2 1 61\nextra",
                                         b"EWA1 2 1 61\x00\n", b"x" * 300)):
            work = workspace(f"damaged_{index}")
            (work / "request.lock").mkdir()
            (work / "request").write_bytes(damaged)
            rejected = run(work, "consume")
            assert "CALLS 0" in rejected.stdout and "stage=rejected" in rejected.stdout, rejected.stdout
            assert "rejected" in (work / "request.ack").read_text()
            assert not (work / "request.lock").exists()

        work = workspace("legacy")
        assert "stage=queued" in run(work, "legacy").stdout
        assert "event_id=87 stage=applied" in run(work, "consume").stdout
        print("PASS: 10 IPC events, safety-floor rejection, live/cross-process ACK and cleanup recovery without replay, concurrent ownership, fail-closed unknown claims, invalid input and I/O faults")


if __name__ == "__main__":
    main()
