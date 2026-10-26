/* SPDX-License-Identifier: Apache-2.0 */
#ifndef EDGE_WALKER_RADAR_DIAG_H
#define EDGE_WALKER_RADAR_DIAG_H

#include <stddef.h>
#include "ew_safety.h"

#define EW_RADAR_DIAG_MAX_BYTES 1024u

/* Pure bounded diagnostics from an already-copied safety snapshot. No UART
 * access, AT, parser reset, logging, allocation or actuator operation.
 * IDs are 1..48 ASCII letters/digits/_/-. Error leaves no partial output. */
int ew_radar_diag_format(char *out, size_t capacity, const char *request_id,
                        const ew_safety_snapshot_t *snapshot);

#endif
