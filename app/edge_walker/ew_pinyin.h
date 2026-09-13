/****************************************************************************
 * 简易拼音：词组 + 音节选字（无整表输入法）
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_PINYIN_H
#define EDGE_WALKER_EW_PINYIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* 从 start 起最多填 max 个候选。out[i] 为词或单字；cons[i] 为吃掉的拼音字母数。 */
int ew_pinyin_lookup(const char *py, int start, char out[][20],
                     unsigned cons[], int max);

#ifdef __cplusplus
}
#endif

#endif
