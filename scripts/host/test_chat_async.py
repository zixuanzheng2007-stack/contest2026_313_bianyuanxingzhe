"""Execute real chat code with resource failures and stale replies."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def body(source, marker):
    first = source.index(marker)
    return source[first:source.index('\n}', first) + 2]


def main():
    source = (ROOT/'app/edge_walker/ew_chat.c').read_text(encoding='utf-8')
    program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include "ew_llm.h"
#define EW_CHAT_TEXT_MAX 2048
typedef struct { unsigned generation; char prompt[256]; } ew_ask_job_t;
static int g_busy, g_reply_ready, fail_allocation, network_calls, thread_calls;
static unsigned g_ask_generation;
static char g_pending[256], g_reply[EW_CHAT_TEXT_MAX];
static void *g_wait_bubble, *g_list, *g_status;
static pthread_mutex_t g_reply_mu = PTHREAD_MUTEX_INITIALIZER;
static void add_bubble(const char *text, int mine) { (void)text;(void)mine; }
static void *lv_obj_get_child(void *list,int32_t index) { (void)list;(void)index;return NULL; }
static unsigned lv_obj_get_child_count(void *list) { (void)list;return 1; }
static void lv_label_set_text(void *label,const char *text) { (void)label;(void)text; }
static void hide_kb(void) {}
static const char *local_reply(const char *text) { (void)text;return NULL; }
ew_llm_result_t ew_llm_ask(const char *prompt,char *out,unsigned size) {
  (void)prompt;network_calls++;snprintf(out,size,"network reply");return EW_LLM_OK;
}
static void *fixture_malloc(size_t size) { return fail_allocation ? NULL : malloc(size); }
static int fixture_create(pthread_t *id,const pthread_attr_t *attr,void *(*worker)(void*),void *arg) {
  (void)id;(void)attr;(void)worker;(void)arg;thread_calls++;return EAGAIN;
}
#define malloc fixture_malloc
#define pthread_create fixture_create
''' + body(source, 'static void *ask_thread(') + '\n' + body(source, 'static void start_ask(') + r'''
#undef malloc
#undef pthread_create
int main(void) {
  ew_ask_job_t *job;
  fail_allocation=1;start_ask("question");
  assert(g_reply_ready && g_reply[0] && network_calls==0 && thread_calls==0);
  fail_allocation=0;g_busy=0;g_reply_ready=0;start_ask("question");
  assert(g_reply_ready && g_reply[0] && network_calls==0 && thread_calls==1);
  snprintf(g_reply,sizeof(g_reply),"new page");g_reply_ready=0;
  job=malloc(sizeof(*job));assert(job);job->generation=g_ask_generation-1;
  snprintf(job->prompt,sizeof(job->prompt),"old question");ask_thread(job);
  assert(!g_reply_ready && strcmp(g_reply,"new page")==0);
  job=malloc(sizeof(*job));assert(job);job->generation=g_ask_generation;
  snprintf(job->prompt,sizeof(job->prompt),"current question");ask_thread(job);
  assert(g_reply_ready && strcmp(g_reply,"network reply")==0);
  puts("PASS real chat: no network on resource failure; late reply isolation");
  return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='ew_chat_async_') as directory:
        folder = Path(directory)
        (folder/'test.c').write_text(program, encoding='utf-8')
        exe = folder/'test.exe'
        subprocess.run(['gcc','-std=c99','-Wall','-Wextra','-Werror',
                        '-I',str(ROOT/'app/edge_walker'),str(folder/'test.c'),
                        '-pthread','-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=5)


if __name__ == '__main__':
    main()
