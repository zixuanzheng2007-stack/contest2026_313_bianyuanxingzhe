/* SPDX-License-Identifier: Apache-2.0 */
/* Synthetic host regression; this is not road or hardware acceptance data. */
#include "ew_ld2451.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(test, label) do { if (!(test)) { \
  printf("FAIL %s (line %d)\n", label, __LINE__); failures++; } } while (0)
static const uint8_t official[] = {
  0xf4,0xf3,0xf2,0xf1,0x11,0,3,1,
  0x8a,0x28,0,0x3c,0x15,0x8a,0x1e,1,0x3c,0x0f,
  0x76,0x5f,0,0x3c,0x0f,0xf8,0xf7,0xf6,0xf5
};
/* Five bytes per target: angle+128, metres, direction, km/h, SNR. */
static unsigned frame(uint8_t *out, unsigned count, unsigned alarm,
                      const uint8_t *targets)
{
  unsigned body = 2 + 5 * count;
  static const uint8_t hdr[] = {0xf4,0xf3,0xf2,0xf1};
  static const uint8_t tail[] = {0xf8,0xf7,0xf6,0xf5};
  memcpy(out,hdr,4); out[4]=(uint8_t)body; out[5]=0;
  out[6]=(uint8_t)count; out[7]=(uint8_t)alarm;
  if (count) memcpy(out+8,targets,5*count);
  memcpy(out+6+body,tail,4);
  return body+10;
}
static ew_track_t track(float range, float speed, float snr)
{
  ew_track_t t;
  memset(&t,0,sizeof(t)); t.valid=t.approaching=true;
  t.range_m=range; t.speed_kmh=speed; t.snr=snr;
  t.ttc_s=-1.0f; /* Caller TTC is deliberately not authoritative. */
  return t;
}
static ew_track_t parse(const uint8_t *data, unsigned len,
                        ew_alert_level_t want, bool want_track)
{
  ew_track_t t;
  ew_sniff_stats_t st={0};
  bool got;
  ew_ld2451_reset();
  got=ew_ld2451_feed_sniff(data,len,&st,&t);
  CHECK(got==want_track,"parser track presence");
  if (want_track) {
    CHECK(t.valid,"parser valid flag");
    CHECK(ew_decide(&t).level==want,"parser decision level");
  }
  return t;
}
static void parser_cases(void)
{
  uint8_t one[64],two[64],batch[256],malformed[128];
  uint8_t target[]={128,22,EW_DIR_APPROACH,20,30};
  uint8_t multiple[]={128,12,EW_DIR_APPROACH,5,30,
                       128,20,EW_DIR_APPROACH,120,30};
  unsigned n,m,split,i;
  ew_track_t t;
  ew_sniff_stats_t st;
  parse(official,sizeof(official),EW_ALERT_STRONG,true);
  n=frame(one,1,0,target); parse(one,n,EW_ALERT_SOFT,true);
  target[1]=12; target[3]=25;
  m=frame(two,1,0,target); parse(two,m,EW_ALERT_STRONG,true);
  target[1]=6; target[3]=40;
  m=frame(two,1,0,target); parse(two,m,EW_ALERT_EMERGENCY,true);
  target[2]=EW_DIR_AWAY;
  m=frame(two,1,0,target); parse(two,m,EW_ALERT_NONE,false);
  m=frame(two,1,1,target); t=parse(two,m,EW_ALERT_SOFT,true);
  CHECK(!strcmp(ew_decide(&t).reason,"radar_alarm"),"module alarm direction compatibility");
  target[2]=EW_DIR_APPROACH; target[3]=3;
  m=frame(two,1,1,target); parse(two,m,EW_ALERT_SOFT,true);
  target[3]=40; target[4]=3;
  m=frame(two,1,1,target); parse(two,m,EW_ALERT_SOFT,true);
  m=frame(two,2,0,multiple); t=parse(two,m,EW_ALERT_EMERGENCY,true);
  CHECK(t.range_m==20.0f,"far fast target outranks near slow target");
  multiple[1]=12; multiple[3]=15; multiple[6]=20; multiple[8]=40;
  m=frame(two,2,0,multiple); t=parse(two,m,EW_ALERT_STRONG,true);
  CHECK(t.range_m==20.0f,"same severity shorter TTC wins");
  multiple[1]=12; multiple[3]=20; multiple[6]=24; multiple[8]=40;
  m=frame(two,2,0,multiple); t=parse(two,m,EW_ALERT_STRONG,true);
  CHECK(t.range_m==12.0f,"equal severity and TTC nearer wins");
  for (split=1;split<n;split++) {
    ew_ld2451_reset(); memset(&st,0,sizeof(st));
    CHECK(!ew_ld2451_feed_sniff(one,split,&st,&t),"partial frame not emitted");
    CHECK(ew_ld2451_feed_sniff(one+split,n-split,&st,&t),"fragmented frame reconstructed");
    CHECK(st.frames_ok==1 && st.bytes_in==n,"fragmented stats");
  }
  ew_ld2451_reset(); memset(&st,0,sizeof(st));
  for (i=0;i<n;i++) {
    bool got=ew_ld2451_feed_sniff(one+i,1,&st,&t);
    CHECK(got==(i+1==n),"single-byte delivery");
  }
  multiple[1]=12; multiple[3]=5; multiple[6]=20; multiple[8]=120;
  m=frame(two,2,0,multiple);
  memcpy(batch,one,n); memcpy(batch+n,two,m);
  t=parse(batch,n+m,EW_ALERT_EMERGENCY,true);
  CHECK(t.range_m==20.0f,"batched frames preserve highest risk");
  m=frame(two,0,0,NULL); memcpy(batch,one,n); memcpy(batch+n,two,m);
  t=parse(batch,n+m,EW_ALERT_SOFT,true);
  CHECK(t.range_m==22.0f,"trailing empty frame does not erase batch target");
  batch[0]=0x12; batch[1]=0xf4; memcpy(batch+2,one,n);
  parse(batch,n+2,EW_ALERT_SOFT,true);
  memcpy(batch,one,n-4); memcpy(batch+n-4,one,n);
  ew_ld2451_reset(); memset(&st,0,sizeof(st));
  CHECK(ew_ld2451_feed_sniff(batch,2*n-4,&st,&t),"bad tail resynchronizes");
  CHECK(st.frames_ok==1 && st.frames_bad>=1,"bad tail rejected in stats");
  for (i=0;i<6;i++) {
    memcpy(malformed,one,n);
    if (i==0) malformed[6]=2;       /* Count larger than body. */
    if (i==1) malformed[6]=0;       /* Trailing target with zero count. */
    if (i==2) malformed[6]=6;       /* Above supported maximum. */
    if (i==3) malformed[7]=2;       /* Invalid alarm. */
    if (i==4) malformed[10]=2;      /* Invalid direction. */
    if (i==5) malformed[n-1]=0;     /* Broken tail. */
    memcpy(malformed+n,one,n);
    ew_ld2451_reset(); memset(&st,0,sizeof(st));
    CHECK(ew_ld2451_feed_sniff(malformed,2*n,&st,&t),"malformed then valid recovers");
    CHECK(st.frames_ok==1 && st.frames_bad>=1,"malformed not counted as frame");
  }
  for (i=0;i<3;i++) {
    const uint8_t lengths[]={1,3,65};
    memcpy(malformed,one,6); malformed[4]=lengths[i];
    memcpy(malformed+6,one,n);
    ew_ld2451_reset(); memset(&st,0,sizeof(st));
    CHECK(ew_ld2451_feed_sniff(malformed,n+6,&st,&t),"invalid length resynchronizes");
    CHECK(st.frames_ok==1 && st.frames_bad>=1,"invalid length statistics");
  }
  {
    ew_ld2451_parser_t first,second;
    ew_sniff_stats_t first_stats={0},second_stats={0};
    ew_ld2451_parser_reset(&first); ew_ld2451_parser_reset(&second);
    CHECK(!ew_ld2451_parser_feed_sniff(&first,one,8,&first_stats,&t),
          "first parser retains its partial frame");
    CHECK(ew_ld2451_parser_feed_sniff(&second,one,n,&second_stats,&t),
          "second UART context is independent");
    ew_ld2451_reset(); /* Diagnostics must not reset another UART owner. */
    CHECK(ew_ld2451_parser_feed_sniff(&first,one+8,n-8,&first_stats,&t),
          "legacy reset cannot corrupt private UART parser");
    CHECK(first_stats.frames_ok==1 && second_stats.frames_ok==1,
          "independent UART statistics");
    CHECK(!ew_ld2451_parser_feed_sniff(NULL,one,n,NULL,NULL),"NULL parser safe");
    CHECK(!ew_ld2451_feed_sniff(NULL,1,NULL,NULL),"NULL input safe");
  }
  printf("  parser: fragments, risk ordering, malformed recovery, alarm fallback\n");
}
static void decision_cases(void)
{
  ew_track_t t;
  ew_decision_t d;
  const float distances[]={8,8.001f,15,15.001f,25,25.001f};
  const ew_alert_level_t levels[]={EW_ALERT_EMERGENCY,EW_ALERT_STRONG,
    EW_ALERT_STRONG,EW_ALERT_SOFT,EW_ALERT_SOFT,EW_ALERT_NONE};
  const float bad[]={NAN,INFINITY,-INFINITY,-1.0f,256.0f};
  unsigned i,j;
  for (i=0;i<sizeof(distances)/sizeof(distances[0]);i++) {
    t=track(distances[i],EW_MIN_SPEED_KMH,EW_MIN_SNR);
    CHECK(ew_decide(&t).level==levels[i],"distance inclusive boundary");
  }
  t=track(90,216,30);
  CHECK(ew_decide(&t).level==EW_ALERT_STRONG,"TTC emergency boundary exclusive");
  t.speed_kmh=217;
  CHECK(ew_decide(&t).level==EW_ALERT_EMERGENCY,"TTC below emergency");
  t.speed_kmh=108;
  CHECK(ew_decide(&t).level==EW_ALERT_SOFT,"TTC strong boundary exclusive");
  t.speed_kmh=109;
  CHECK(ew_decide(&t).level==EW_ALERT_STRONG,"TTC below strong");
  t=track(100,72,30);
  CHECK(ew_decide(&t).level==EW_ALERT_SOFT,"TTC soft boundary inclusive");
  t.speed_kmh=71;
  CHECK(ew_decide(&t).level==EW_ALERT_NONE,"TTC above soft");
  t=track(6,EW_MIN_SPEED_KMH,EW_MIN_SNR);
  CHECK(ew_decide(&t).level==EW_ALERT_EMERGENCY,"minimum speed SNR inclusive");
  t.speed_kmh-=0.001f;
  CHECK(ew_decide(&t).level==EW_ALERT_NONE,"below speed minimum");
  t=track(6,40,EW_MIN_SNR-0.001f);
  CHECK(ew_decide(&t).level==EW_ALERT_NONE,"below SNR minimum");
  t=track(0,40,30);
  CHECK(ew_decide(&t).level==EW_ALERT_EMERGENCY,"zero range conservative decision");
  t=track(255,255,255); t.azimuth_deg=-128;
  CHECK(strcmp(ew_decide(&t).reason,"invalid_track"),"physical maximum and azimuth minimum valid");
  t.azimuth_deg=127;
  CHECK(strcmp(ew_decide(&t).reason,"invalid_track"),"azimuth maximum valid");
  t=track(100,0,30); d=ew_decide(&t);
  CHECK(d.level==EW_ALERT_NONE && d.ttc_s<0,"zero speed no TTC");
  t=track(100,10,30);
  for (i=0;i<4;i++) {
    t.ttc_s=bad[i]; d=ew_decide(&t);
    CHECK(d.level==EW_ALERT_NONE && isfinite(d.ttc_s) && d.ttc_s>30,
          "caller TTC ignored and recomputed");
  }
  t.ttc_s=0;
  CHECK(ew_decide(&t).level==EW_ALERT_NONE,"forged TTC cannot raise alert");
  for (i=0;i<3;i++) for (j=0;j<5;j++) {
    t=track(6,40,30);
    if (i==0) t.range_m=bad[j];
    if (i==1) t.speed_kmh=bad[j];
    if (i==2) t.snr=bad[j];
    d=ew_decide(&t);
    CHECK(d.level==EW_ALERT_NONE && !strcmp(d.reason,"invalid_track"),
          "invalid physical value rejected");
    t.radar_alarm=true; d=ew_decide(&t);
    CHECK(d.level==EW_ALERT_SOFT && isfinite(d.range_m) && isfinite(d.speed_kmh)
          && isfinite(d.ttc_s) && !strcmp(d.reason,"radar_alarm_invalid_track"),
          "invalid physical module alarm fallback sanitized");
  }
  for (j=0;j<5;j++) {
    const float azimuth_bad[]={NAN,INFINITY,-INFINITY,-129,128};
    t=track(6,40,30); t.azimuth_deg=azimuth_bad[j];
    CHECK(ew_decide(&t).level==EW_ALERT_NONE,"invalid azimuth rejected");
  }
  CHECK(ew_decide(NULL).level==EW_ALERT_NONE,"NULL track safe");
  t.valid=false; CHECK(ew_decide(&t).level==EW_ALERT_NONE,"invalid track flag");
  printf("  decide: default boundaries, recomputed TTC, physical validation\n");
}
static uint32_t confirm(ew_hold_t *h,uint32_t first,const ew_track_t *t)
{
  unsigned i;
  ew_decision_t d;
  for (i=0;i<EW_CONFIRM_FRAMES;i++) {
    d=ew_hold_update(h,first+i*10u,true,true,t);
    CHECK(d.level==(i+1==EW_CONFIRM_FRAMES ? ew_decide(t).level : EW_ALERT_NONE),
          "fresh confirmation count");
  }
  return first+(EW_CONFIRM_FRAMES-1u)*10u;
}
static void hold_cases(void)
{
  ew_hold_t h;
  ew_track_t em=track(6,40,30),soft=track(22,20,30);
  ew_decision_t d;
  uint32_t last;
  unsigned i;
  ew_hold_reset(&h); d=ew_hold_update(&h,0,false,false,NULL);
  CHECK(d.level==EW_ALERT_NONE && d.link==EW_LINK_DEAD,"initial link dead");
  d=ew_hold_update(&h,10,true,false,NULL);
  CHECK(d.link==EW_LINK_NOISE,"bytes without frame noise");
  d=ew_hold_update(&h,20,true,true,NULL);
  CHECK(d.level==EW_ALERT_NONE && d.link==EW_LINK_OK,"empty frame link OK");
  ew_hold_reset(&h); d=ew_hold_update(&h,100,true,true,&em);
  for (i=0;i<EW_CONFIRM_FRAMES+2u;i++) {
    d=ew_hold_update(&h,101+i,false,false,&em);
    CHECK(h.pending_hits==1,"repeated pointer neither increases nor resets hits");
  }
  CHECK(d.level==(EW_CONFIRM_FRAMES==1 ? EW_ALERT_EMERGENCY : EW_ALERT_NONE),
        "repeated track cannot bypass frame confirmation");
  for (i=1;i<EW_CONFIRM_FRAMES;i++) d=ew_hold_update(&h,120+i,true,true,&em);
  CHECK(d.level==EW_ALERT_EMERGENCY,"confirmation survives no-frame polling");
  if (EW_CONFIRM_FRAMES>1) {
    ew_hold_reset(&h); ew_hold_update(&h,100,true,true,&em);
    ew_hold_update(&h,110,true,true,NULL);
    CHECK(h.pending_hits==0,"fresh empty breaks pending confirmation");
    for (i=0;i+1u<EW_CONFIRM_FRAMES;i++) {
      d=ew_hold_update(&h,120+i,true,true,&em);
      CHECK(d.level==EW_ALERT_NONE,"confirmation restarts after empty");
    }
    ew_hold_reset(&h); ew_hold_update(&h,100,true,true,&em);
    d=ew_hold_update(&h,100+EW_LINK_STALE_MS+1u,true,true,&em);
    CHECK(h.pending_hits==1 && d.level==EW_ALERT_NONE,"stale gap breaks confirmation");
  }
  ew_hold_reset(&h); last=confirm(&h,100,&em);
  for (i=0;i<EW_CONFIRM_FRAMES+1u;i++) {
    d=ew_hold_update(&h,last+10+i,true,true,&soft);
    CHECK(d.level==EW_ALERT_EMERGENCY && d.range_m==em.range_m &&
          d.speed_kmh==em.speed_kmh && strstr(d.reason,"emergency"),
          "weak frame cannot lower level or replace metadata");
  }
  d=ew_hold_update(&h,last+EW_CLEAR_MS,true,true,&soft);
  CHECK(d.level==EW_ALERT_SOFT && d.range_m==soft.range_m,
        "confirmed weaker level only after high-level hold time");
  d=ew_hold_update(&h,last+EW_CLEAR_MS+1,true,true,&em);
  CHECK(d.level==EW_ALERT_EMERGENCY,"latched alarm escalates immediately");
  /* A confirmed weaker target remains meaningful at the expiry poll even
   * without a new frame; its age must stay tied to the actual support frame. */
  ew_hold_reset(&h); last=confirm(&h,100,&em);
  for (i=0;i<EW_CONFIRM_FRAMES;i++)
    ew_hold_update(&h,last+EW_CLEAR_MS-100u+i,true,true,&soft);
  d=ew_hold_update(&h,last+EW_CLEAR_MS,false,false,&em);
  CHECK(d.level==EW_ALERT_SOFT && d.range_m==soft.range_m,
        "expiry poll uses already-confirmed fresh weaker evidence");
  d=ew_hold_update(&h,last+2u*EW_CLEAR_MS-100u+EW_CONFIRM_FRAMES-1u,
                   false,false,&em);
  CHECK(d.level==EW_ALERT_NONE,"weaker evidence timeout uses its actual frame time");
  ew_hold_reset(&h); last=confirm(&h,100,&em);
  d=ew_hold_update(&h,last+EW_CLEAR_MS-1,false,false,&em);
  CHECK(d.level==EW_ALERT_EMERGENCY,"clear boundary before expiry");
  d=ew_hold_update(&h,last+EW_CLEAR_MS,false,false,&em);
  CHECK(d.level==EW_ALERT_NONE,"reused track cannot postpone clear");
  d=ew_hold_update(&h,last+EW_LINK_STALE_MS,false,false,NULL);
  CHECK(d.link==EW_LINK_OK,"frame freshness inclusive boundary");
  d=ew_hold_update(&h,last+EW_LINK_STALE_MS+1,false,false,NULL);
  CHECK(d.link==EW_LINK_DEAD && !strcmp(d.reason,"no_uart"),"stale bytes and frame no_uart");
  d=ew_hold_update(&h,last+EW_LINK_STALE_MS+2,true,false,NULL);
  CHECK(d.link==EW_LINK_NOISE && !strcmp(d.reason,"no_frame"),"noise cannot renew frame age");
  ew_hold_reset(&h); last=confirm(&h,UINT32_MAX-100u,&em);
  d=ew_hold_update(&h,last+EW_CLEAR_MS-1u,false,false,NULL);
  CHECK(d.level==EW_ALERT_EMERGENCY,"wrap before clear");
  d=ew_hold_update(&h,last+EW_CLEAR_MS,false,false,NULL);
  CHECK(d.level==EW_ALERT_NONE,"wrap clear expiry");
  d=ew_hold_update(&h,last+EW_LINK_STALE_MS+1u,false,false,NULL);
  CHECK(d.link==EW_LINK_DEAD,"wrap frame staleness");
  d=ew_hold_update(NULL,0,false,false,NULL);
  CHECK(d.level==EW_ALERT_NONE && d.link==EW_LINK_DEAD,"NULL hold safe");
  printf("  hold: confirm=%d, fresh frames, metadata, clear/stale/wrap\n",EW_CONFIRM_FRAMES);
}
int main(void)
{
  printf("edge_walker synthetic radar safety regression\n");
  parser_cases(); decision_cases(); hold_cases();
  if (failures) { printf("%d FAIL\n",failures); return 1; }
  printf("ALL PASS\n"); return 0;
}
