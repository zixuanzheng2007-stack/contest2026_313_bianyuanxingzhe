/* SPDX-License-Identifier: Apache-2.0 */
#ifndef EDGE_WALKER_SNAPSHOT_H
#define EDGE_WALKER_SNAPSHOT_H

#include <stddef.h>
#include "ew_safety.h"

/* Pure bounded serialization. IDs: 1..48 ASCII letters/digits/_/-. No I/O.
 * Returns bytes or negative errno; errors leave no usable partial output. */
int ew_snapshot_format(char *out, size_t capacity, const char *request_id,
                       const ew_safety_snapshot_t *snapshot,
                       unsigned long snapshot_seq);

#endif
