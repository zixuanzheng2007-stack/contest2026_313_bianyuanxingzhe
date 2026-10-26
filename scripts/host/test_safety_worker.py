# SPDX-License-Identifier: Apache-2.0
"""Run the production pthread radar worker without UI, networking or hardware."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/edge_walker"

WORKER_HARNESS = r'''
#include "ew_safety.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* Only physical output and event-id allocation are substitutes. There are
 * deliberately no UI tick, LVGL, network, IPC, or Agent-dispatch definitions. */
static pthread_mutex_t stub_lock=PTHREAD_MUTEX_INITIALIZER;
static unsigned prepares,setters,foreign_workers;
static unsigned long next_id;
static int floor_level;
static const unsigned char emergency[]={
  0xf4,0xf3,0xf2,0xf1,7,0,1,0,128,6,0,40,30,0xf8,0xf7,0xf6,0xf5};
static bool have_worker;
static pthread_t worker_id;
int alert_buzzer_prepare(void) {
  __atomic_add_fetch(&prepares,1,__ATOMIC_RELAXED); return 0;
}
void alert_buzzer_safety_level(ew_alert_level_t level) {
  pthread_mutex_lock(&stub_lock);
  if (!have_worker) { worker_id=pthread_self(); have_worker=true; }
  else if (!pthread_equal(worker_id,pthread_self())) foreign_workers++;
  setters++; floor_level=(int)level;
  pthread_mutex_unlock(&stub_lock);
}
unsigned long ew_agent_next_event_id(void) {
  return __atomic_add_fetch(&next_id,1,__ATOMIC_RELAXED);
}
static uint32_t now_ms(void) {
  struct timespec ts;
  assert(clock_gettime(CLOCK_MONOTONIC,&ts)==0);
  return (uint32_t)((uint64_t)ts.tv_sec*1000u+ts.tv_nsec/1000000u);
}
static int floor_value(void) {
  int value;
  pthread_mutex_lock(&stub_lock); value=floor_level; pthread_mutex_unlock(&stub_lock);
  return value;
}
static void append_frames(unsigned count) {
  FILE *file=fopen(EW_RADAR_DEV,"ab");
  unsigned i;
  assert(file);
  for (i=0;i<count;i++) assert(fwrite(emergency,1,sizeof(emergency),file)==sizeof(emergency));
  assert(fclose(file)==0);
}
static ew_safety_snapshot_t wait_level(ew_alert_level_t level,uint32_t minimum_frames) {
  ew_safety_snapshot_t snap;
  uint32_t started=now_ms();
  do {
    ew_safety_snapshot(&snap);
    if (snap.running && snap.sniff.frames_ok>=minimum_frames && snap.decision.level==level)
      return snap;
    usleep(1000);
  } while ((uint32_t)(now_ms()-started)<2000u);
  fprintf(stderr,"worker timeout: want level=%d frames>=%lu; actual level=%d frames=%lu error=%d\n",
    (int)level,(unsigned long)minimum_frames,(int)snap.decision.level,
    (unsigned long)snap.sniff.frames_ok,snap.radar_error);
  exit(3);
}
static void *start_again(void *unused) {
  unsigned i; (void)unused;
  for(i=0;i<10;i++) assert(ew_safety_start()==0);
  return NULL;
}
static void idempotent_start(void) {
  pthread_t callers[8]; unsigned i;
  for(i=0;i<8;i++) assert(pthread_create(callers+i,NULL,start_again,NULL)==0);
  for(i=0;i<8;i++) assert(pthread_join(callers[i],NULL)==0);
  assert(__atomic_load_n(&prepares,__ATOMIC_RELAXED)==1);
}
int main(int argc,char **argv) {
  ew_safety_snapshot_t first,active,cleared,later;
  ew_safety_event_t event;
  unsigned i,count=0;
  unsigned long last_id=0;
  bool saw_emergency=false,saw_clear=false;
  const char *mode=argc>1 ? argv[1] : "normal";
  if(strcmp(mode,"missing")) {
    FILE *empty=fopen(EW_RADAR_DEV,"wb"); assert(empty); assert(fclose(empty)==0);
  }
  ew_safety_snapshot(NULL); assert(!ew_safety_take_event(NULL));
  idempotent_start();
  if(!strcmp(mode,"missing")) {
    uint32_t started=now_ms();
    do { ew_safety_snapshot(&first); usleep(1000); }
    while(first.radar_error!=ENOENT && (uint32_t)(now_ms()-started)<2000u);
    assert(first.radar_error==ENOENT && first.running);
  }
  append_frames(EW_CONFIRM_FRAMES);
  active=wait_level(EW_ALERT_EMERGENCY,EW_CONFIRM_FRAMES);
  assert(active.ever_bytes && active.ever_frame && active.radar_error==0);
  assert(active.decision.range_m==6.0f && active.decision.speed_kmh==40.0f);
  assert(active.event_id!=0 && floor_value()==EW_ALERT_EMERGENCY);
  idempotent_start();
  cleared=wait_level(EW_ALERT_NONE,EW_CONFIRM_FRAMES);
  assert(floor_value()==EW_ALERT_NONE);
  assert(cleared.updated_ms!=active.updated_ms && cleared.running);
  assert(cleared.sniff.bytes_in==17u*EW_CONFIRM_FRAMES);
  assert(cleared.sample_total==cleared.sniff.bytes_in);
  assert(cleared.sample_bytes==17u*EW_CONFIRM_FRAMES && cleared.read_calls>0);
  for(i=0;i<cleared.sample_bytes;i++)
    assert(cleared.sample[i]==emergency[i%sizeof(emergency)]);
  first=cleared;
  usleep(30000); ew_safety_snapshot(&later);
  assert(later.updated_ms!=first.updated_ms); /* No UI/network calls ran. */
  if(strcmp(mode,"overflow")) {
    uint32_t started=now_ms();
    do { ew_safety_snapshot(&later); usleep(1000); }
    while(later.decision.link!=EW_LINK_DEAD && (uint32_t)(now_ms()-started)<2000u);
    assert(later.decision.link==EW_LINK_DEAD && later.decision.level==EW_ALERT_NONE);
    assert(!strcmp(later.decision.reason,"no_uart") && later.ever_frame);
    assert(later.sniff.frames_ok==EW_CONFIRM_FRAMES && floor_value()==EW_ALERT_NONE);
  }
  if(!strcmp(mode,"overflow")) {
    /* Leave all events undrained: backlogged telemetry must not stop safety. */
    for(i=0;i<18;i++) {
      append_frames(EW_CONFIRM_FRAMES);
      active=wait_level(EW_ALERT_EMERGENCY,(i+2u)*EW_CONFIRM_FRAMES);
      assert(floor_value()==EW_ALERT_EMERGENCY);
      cleared=wait_level(EW_ALERT_NONE,(i+2u)*EW_CONFIRM_FRAMES);
    }
    ew_safety_snapshot(&later);
    assert(later.dropped_events>0);
    assert(later.sample_total==19u*17u*EW_CONFIRM_FRAMES);
    assert(later.sample_bytes==64 && later.read_max_gap_ms>0);
    for(i=0;i<later.sample_bytes;i++)
      assert(later.sample[i]==emergency[(later.sample_total-64u+i)%sizeof(emergency)]);
  }
  while(ew_safety_take_event(&event)) {
    assert(event.event_id>last_id); last_id=event.event_id; count++;
    if(event.decision.level==EW_ALERT_EMERGENCY) saw_emergency=true;
    if(saw_emergency && event.decision.level==EW_ALERT_NONE) saw_clear=true;
  }
  assert(saw_emergency && saw_clear && count>=2);
  if(!strcmp(mode,"overflow")) assert(count==32);
  pthread_mutex_lock(&stub_lock);
  assert(setters>2 && foreign_workers==0);
  pthread_mutex_unlock(&stub_lock);
  printf("PASS real worker %s confirm=%d: autonomous emergency/clear, snapshot, single UART owner, events=%u drops=%lu\n",
    mode,EW_CONFIRM_FRAMES,count,(unsigned long)later.dropped_events);
  return 0;
}
'''

BUZZER_HARNESS = r'''
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
static unsigned writes;
static void record_pin_write(int state) { (void)state; writes++; }
static int fake_create(pthread_t *thread,const pthread_attr_t *attr,
                       void *(*entry)(void *),void *arg) {
  (void)attr; (void)entry; (void)arg; *thread=pthread_self(); return 0;
}
static int fake_detach(pthread_t thread) { (void)thread; return 0; }
#define pthread_create fake_create
#define pthread_detach fake_detach
#include "alert_buzzer.c"
#undef pthread_create
#undef pthread_detach
int main(void) {
  unsigned before;
  assert(alert_buzzer_prepare()==0 && active_freq()==0);
  alert_buzzer_safety_level(EW_ALERT_EMERGENCY);
  assert(active_freq()==2700);
  before=writes;
  alert_buzzer_level(EW_ALERT_NONE);
  assert(active_freq()==2700 && writes==before);
  alert_buzzer_level(EW_ALERT_SOFT); assert(active_freq()==2700);
  alert_buzzer_level(EW_ALERT_STRONG); assert(active_freq()==2700);
  alert_buzzer_stop(); assert(active_freq()==2700);
  alert_buzzer_set_alert(4000); assert(active_freq()==4000);
  alert_buzzer_safety_level(EW_ALERT_STRONG); assert(active_freq()==4000);
  alert_buzzer_safety_level(EW_ALERT_NONE); assert(active_freq()==4000);
  alert_buzzer_level(EW_ALERT_NONE); assert(active_freq()==0);
  alert_buzzer_safety_level(EW_ALERT_SOFT); assert(active_freq()==2300);
  assert(alert_buzzer_beep(2500,120)==-EBUSY);
  alert_buzzer_safety_level(EW_ALERT_NONE); assert(active_freq()==0);
  puts("PASS production buzzer max(manual,safety): manual NONE cannot suppress floor");
  return 0;
}
'''

HAL_HEADER = r'''
typedef struct { unsigned Mode,Pin,Pull; } GPIO_InitTypeDef;
typedef enum { GPIO_PIN_RESET=0,GPIO_PIN_SET=1 } GPIO_PinState;
#define PAD_PA28 28
#define GPIO_A28 28
#define PIN_NOPULL 0
#define GPIO_MODE_OUTPUT 1
#define GPIO_NOPULL 0
#define hwp_gpio1 ((void *)0)
static inline void HAL_PIN_Set(int pad,int pin,int pull,int function) {
  (void)pad; (void)pin; (void)pull; (void)function;
}
static inline void HAL_PIN_Set_DS0(int pad,int v,int f) { (void)pad; (void)v; (void)f; }
static inline void HAL_PIN_Set_DS1(int pad,int v,int f) { (void)pad; (void)v; (void)f; }
static inline void HAL_GPIO_Init(void *gpio,GPIO_InitTypeDef *init) { (void)gpio; (void)init; }
static inline void HAL_GPIO_WritePin(void *gpio,unsigned pin,GPIO_PinState state) {
  (void)gpio; (void)pin; record_pin_write((int)state);
}
'''


class SafetyWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("gcc")
        if compiler is None:
            raise RuntimeError("GCC required; safety worker tests cannot be skipped")
        os.environ["PATH"] = str(Path(compiler).parent) + os.pathsep + os.environ.get("PATH", "")
        cls.temp = tempfile.TemporaryDirectory(prefix="ew_safety_worker_")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.path = Path(cls.temp.name)
        harness = cls.path / "worker.c"
        harness.write_text(WORKER_HARNESS, encoding="utf-8")
        cls.executables = {}
        # CRT regular-file reads already return at EOF; Windows has no
        # POSIX O_NONBLOCK constant. Linux uses the genuine flag unchanged.
        platform_flags = ["-DO_NONBLOCK=0"] if os.name == "nt" else []
        for confirm in (1, 3):
            executable = cls.path / (f"worker_{confirm}.exe" if os.name == "nt" else f"worker_{confirm}")
            subprocess.run([
                compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                "-DEW_SAFETY_HOST_TEST", "-DEW_SAFETY_PERIOD_MS=5",
                "-DEW_CLEAR_MS=100", "-DEW_LINK_STALE_MS=150",
                *platform_flags,
                f"-DEW_CONFIRM_FRAMES={confirm}", '-DEW_RADAR_DEV="radar.uart"',
                "-I", str(SOURCE), str(harness), str(SOURCE / "ew_safety.c"),
                str(SOURCE / "ew_ld2451.c"), "-o", str(executable), "-lm",
            ], check=True)
            cls.executables[confirm] = executable
        nuttx = cls.path / "nuttx"
        nuttx.mkdir()
        (nuttx / "config.h").write_text("/* host HAL substitute */\n", encoding="utf-8")
        (nuttx / "arch.h").write_text(
            "static inline void up_udelay(unsigned usec) { (void)usec; }\n", encoding="utf-8")
        (cls.path / "bf0_hal.h").write_text(HAL_HEADER, encoding="utf-8")
        buzzer = cls.path / "buzzer.c"
        buzzer.write_text(BUZZER_HARNESS, encoding="utf-8")
        cls.buzzer = cls.path / ("buzzer.exe" if os.name == "nt" else "buzzer")
        subprocess.run([
            compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
            "-D__NuttX__", "-I", str(cls.path), "-I", str(SOURCE), str(buzzer),
            "-o", str(cls.buzzer),
        ], check=True)

    def run_worker(self, mode: str, confirm: int = 1) -> str:
        working = self.path / f"run_{mode}_{confirm}"
        working.mkdir()
        result = subprocess.run([str(self.executables[confirm]), mode], cwd=working,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS real worker", result.stdout)
        return result.stdout

    def test_autonomous_worker_without_ui_network_or_agent_dispatch(self) -> None:
        self.run_worker("normal")

    def test_three_frames_in_one_uart_read_confirm_three_times(self) -> None:
        self.run_worker("normal", confirm=3)

    def test_uart_missing_then_available_recovers(self) -> None:
        self.run_worker("missing")

    def test_full_event_queue_drops_telemetry_but_keeps_safety_running(self) -> None:
        self.assertIn("events=32", self.run_worker("overflow"))

    def test_actual_buzzer_manual_none_cannot_override_safety_floor(self) -> None:
        result = subprocess.run([str(self.buzzer)], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("manual NONE cannot suppress floor", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
