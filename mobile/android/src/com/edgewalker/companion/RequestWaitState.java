/* SPDX-License-Identifier: Apache-2.0 */
package com.edgewalker.companion;

/** Pure request-wait bookkeeping. Callers must confine access to one thread. */
final class RequestWaitState {
    static final long DEFAULT_TIMEOUT_MS = 12000L;
    static final long ASK_TIMEOUT_MS = 60000L;

    private final long deadline;
    private boolean queued;

    RequestWaitState(String operation, long sentAtElapsedMs) {
        this.deadline = sentAtElapsedMs + ("ask".equals(operation)
                ? ASK_TIMEOUT_MS : DEFAULT_TIMEOUT_MS);
    }

    long deadline() {
        return deadline;
    }

    /** Returns true only for the first accepted/queued transition. */
    boolean markQueued(long nowElapsedMs) {
        if (isExpired(nowElapsedMs) || queued) {
            return false;
        }
        queued = true;
        return true;
    }

    boolean isQueued() {
        return queued;
    }

    /** Preserve the existing watchdog boundary: expiration begins after deadline. */
    boolean isExpired(long nowElapsedMs) {
        return nowElapsedMs > deadline;
    }
}
