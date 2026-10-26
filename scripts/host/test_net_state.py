"""Compile and exercise the pure ew_net_state snapshot contract."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    harness = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ew_net_state.h"
int main(void) {
  ew_net_snapshot_t s;
  assert(ew_net_state_snapshot(&s) == 0);
  ew_net_state_publish(EW_NET_LINK_JOINED, "192.168.43.11");
  assert(ew_net_state_snapshot(&s) == 0);
  assert(s.link == EW_NET_LINK_JOINED);
  assert(strcmp(s.ip, "192.168.43.11") == 0);
  ew_net_state_error(EW_NET_ERR_TIMEOUT);
  assert(ew_net_state_snapshot(&s) == 0);
  assert(s.error == EW_NET_ERR_TIMEOUT && s.generation >= 2);
  puts("PASS: network snapshot ownership and error publication");
  return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="ew_net_state_") as directory:
        path = Path(directory)
        cfile = path / "test.c"
        exe = path / "test"
        cfile.write_text(harness, encoding="utf-8")
        subprocess.run([
            "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "app/edge_walker"), str(cfile),
            str(ROOT / "app/edge_walker/ew_net_state.c"),
            "-pthread", "-o", str(exe),
        ], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
