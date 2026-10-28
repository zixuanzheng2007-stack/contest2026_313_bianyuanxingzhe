package com.edgewalker.companion;

/** Minimal host-side tests; run with javac/java and no Android SDK. */
public final class RequestWaitStateTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        RequestWaitState ordinary = new RequestWaitState("test_alert", 1000L);
        check(ordinary.deadline() == 13000L, "ordinary request must use 12 seconds");
        check(!ordinary.isExpired(13000L), "deadline boundary remains pending");
        check(ordinary.isExpired(13001L), "ordinary request expires after deadline");

        RequestWaitState ask = new RequestWaitState("ask", 500L);
        check(ask.deadline() == 60500L, "ask request must use 60 seconds");
        check(!ask.isExpired(60500L), "ask deadline boundary remains pending");
        check(ask.isExpired(60501L), "ask request expires after deadline");

        RequestWaitState queued = new RequestWaitState("set_profile", 10L);
        check(queued.markQueued(10L), "first queued acknowledgement transitions state");
        long fixedDeadline = queued.deadline();
        for (int i = 0; i < 10000; i++) {
            check(!queued.markQueued(10L), "duplicate queued acknowledgement is idempotent");
        }
        check(queued.isQueued(), "queued state is retained");
        check(queued.deadline() == fixedDeadline, "queued flood cannot extend deadline");
        check(queued.isExpired(fixedDeadline + 1L), "queued flood still expires at original deadline");

        // No watchdog is involved: the state rejects the late queued transition itself.
        RequestWaitState lateQueued = new RequestWaitState("set_profile", 100L);
        check(!lateQueued.markQueued(12101L), "late queued must not confirm reception");
        check(!lateQueued.isQueued(), "late queued must not mutate queued state");
        check(lateQueued.isExpired(12101L), "late applied must be rejected by receiver expiry guard");
        RequestWaitState boundary = new RequestWaitState("set_profile", 100L);
        check(boundary.markQueued(12100L), "exact deadline retains existing inclusive boundary");
        check(!boundary.markQueued(12101L), "queued state must not transition again after deadline");
        RequestWaitState lateAsk = new RequestWaitState("ask", 100L);
        check(!lateAsk.markQueued(60101L), "late ask queued must not confirm reception");
        check(lateAsk.isExpired(60101L), "late ask result must hit receiver expiry guard");

        System.out.println("RequestWaitStateTest: PASS");
    }
}
