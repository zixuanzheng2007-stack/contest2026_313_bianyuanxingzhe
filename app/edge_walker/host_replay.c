/* SPDX-License-Identifier: Apache-2.0 */
/* Offline raw-byte replay through the production parser, decision and hold. */
#include "ew_ld2451.h"
#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LINE_SIZE 65536u
static char line[LINE_SIZE], raw[LINE_SIZE];
static uint8_t bytes[LINE_SIZE / 2];

static int error(unsigned row, const char *message)
{
  fprintf(stderr,"host_replay: input line %u: %s\n",row,message);
  return 2;
}
static char *trim(char *text)
{
  char *end;
  while (isspace((unsigned char)*text)) text++;
  end=text+strlen(text);
  while (end>text && isspace((unsigned char)end[-1])) --end;
  *end='\0';
  return text;
}
/* Two CSV columns; optional quotes permit ordinary CSV writer output. */
static int field(char **cursor, char *out, size_t size)
{
  char *p=*cursor;
  size_t n=0;
  bool quoted;
  while (*p==' ' || *p=='\t') p++;
  quoted=(*p=='"');
  if (quoted) p++;
  while (*p) {
    char c=*p++;
    if (quoted && c=='"') {
      if (*p=='"') p++;
      else {
        while (*p==' ' || *p=='\t') p++;
        if (*p && *p!=',') return -1;
        *cursor=p; out[n]='\0'; return 0;
      }
    } else if (!quoted && c==',') { --p; break; }
    if (n+1>=size) return -1;
    out[n++]=c;
  }
  if (quoted) return -1;
  out[n]='\0'; *cursor=p;
  return 0;
}
static int nibble(unsigned char c)
{
  if (c>='0' && c<='9') return c-'0';
  if (c>='a' && c<='f') return c-'a'+10;
  if (c>='A' && c<='F') return c-'A'+10;
  return -1;
}
static int hex_bytes(const char *p)
{
  size_t n=0;
  int high=-1;
  for (;*p;p++) {
    int v;
    if (isspace((unsigned char)*p)) continue;
    v=nibble((unsigned char)*p);
    if (v<0) return -1;
    if (high<0) high=v;
    else {
      if (n>=sizeof(bytes)) return -1;
      bytes[n++]=(uint8_t)(high*16+v); high=-1;
    }
  }
  return high<0 ? (int)n : -1;
}
static void quoted(const char *value)
{
  putchar('"');
  for (;value && *value;value++) {
    if (*value=='"') putchar('"');
    putchar(*value);
  }
  putchar('"');
}
static const char *link_name(ew_link_t link)
{
  return link==EW_LINK_OK ? "OK" : link==EW_LINK_NOISE ? "NOISE" : "DEAD";
}
static void usage(void)
{
  fprintf(stderr,"Usage: host_replay [input.csv|-]\n"
    "CSV header: timestamp_ms,raw_hex\n"
    "timestamp_ms: uint32 decimal milliseconds; modulo-forward time only.\n"
    "raw_hex: hex byte pairs, contiguous or space separated; empty = time tick.\n"
    "Blank lines and # comments are allowed. Maximum row is 65534 bytes.\n");
}
int main(int argc,char **argv)
{
  FILE *input=stdin;
  ew_hold_t hold;
  ew_sniff_stats_t stats={0};
  unsigned line_number=0,rows=0;
  uint32_t previous=0;
  bool have_previous=false,header=false;
  if (argc>2 || (argc==2 && !strcmp(argv[1],"--help"))) {
    usage(); return argc>2 ? 2 : 0;
  }
  if (argc==2 && strcmp(argv[1],"-")) {
    input=fopen(argv[1],"r");
    if (!input) { perror("host_replay: open input"); return 2; }
  }
  ew_ld2451_reset(); ew_hold_reset(&hold);
  puts("row,timestamp_ms,input_bytes,frames_in_row,frames_ok,frames_bad,level,link,"
       "range_m,speed_kmh,ttc_s,reason,last_frame_level,pending_level,pending_hits");
  while (fgets(line,sizeof(line),input)) {
    char stamp[64],*p,*end,*number;
    unsigned long long time_value;
    uint32_t now,frames_before;
    ew_decision_t decision;
    ew_alert_level_t last_level=EW_ALERT_NONE;
    int count,i;
    line_number++;
    if (!strchr(line,'\n') && !feof(input)) return error(line_number,"row too long");
    p=trim(line);
    if (!line_number) return error(line_number,"line counter overflow");
    if (!*p || *p=='#') continue;
    if (!header && (unsigned char)p[0]==0xef && (unsigned char)p[1]==0xbb &&
        (unsigned char)p[2]==0xbf) p+=3;
    if (field(&p,stamp,sizeof(stamp))<0 || *p++!=',' ||
        field(&p,raw,sizeof(raw))<0 || *p)
      return error(line_number,"expected exactly two CSV columns");
    if (!header) {
      if (strcmp(trim(stamp),"timestamp_ms") || strcmp(trim(raw),"raw_hex"))
        return error(line_number,"expected header timestamp_ms,raw_hex");
      header=true; continue;
    }
    number=trim(stamp);
    if (!isdigit((unsigned char)*number)) return error(line_number,"invalid timestamp");
    errno=0; time_value=strtoull(number,&end,10);
    if (errno || *end || time_value>UINT32_MAX)
      return error(line_number,"timestamp must be decimal uint32 milliseconds");
    now=(uint32_t)time_value;
    if (have_previous && (uint32_t)(now-previous)>INT32_MAX)
      return error(line_number,"timestamps must advance modulo uint32 (gap <= 2147483647ms)");
    count=hex_bytes(raw);
    if (count<0) return error(line_number,"raw_hex contains non-hex text or an unmatched nibble");
    previous=now; have_previous=true; frames_before=stats.frames_ok;
    for (i=0;i<count;i++) {
      ew_track_t candidate;
      uint32_t before=stats.frames_ok;
      bool got=ew_ld2451_feed_sniff(bytes+i,1,&stats,&candidate);
      if (stats.frames_ok!=before) {
        last_level=ew_decide(got ? &candidate : NULL).level;
        ew_hold_update(&hold,now,true,true,got ? &candidate : NULL);
      }
    }
    /* Polling here cannot confirm a reused frame or refresh its alert age. */
    decision=ew_hold_update(&hold,now,count>0,false,NULL);
    rows++;
    printf("%u,%lu,%d,%lu,%lu,%lu,%s,%s,%.3f,%.3f,%.6f,",rows,
           (unsigned long)now,count,(unsigned long)(stats.frames_ok-frames_before),
           (unsigned long)stats.frames_ok,(unsigned long)stats.frames_bad,
           ew_alert_level_name(decision.level),link_name(decision.link),
           decision.range_m,decision.speed_kmh,decision.ttc_s);
    quoted(decision.reason);
    printf(",%s,%s,%u\n",stats.frames_ok!=frames_before ?
      ew_alert_level_name(last_level) : "NO_FRAME",ew_alert_level_name(hold.pending),
      (unsigned)hold.pending_hits);
  }
  if (ferror(input)) { perror("host_replay: read input"); return 2; }
  if (input!=stdin) fclose(input);
  if (!header || !rows) return error(line_number,"input needs a header and at least one data row");
  if (fflush(stdout) || ferror(stdout)) { perror("host_replay: write output"); return 2; }
  return 0;
}
