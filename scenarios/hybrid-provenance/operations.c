#include "model.h"

/* No tracing calls or marker instructions. Volatile preserves the two writes
 * in the overwrite case; the experiment explicitly models these field layouts. */
void choose_value(volatile struct output *dst, const struct input *src, int select) {
    dst->audit = src->noise ^ 0x33u;
    if (select > 0) dst->value = src->secret;
    else dst->value = src->public_value;
}

void overwrite_value(volatile struct output *dst, const struct input *src, int select) {
    dst->value = src->secret;
    dst->audit = src->noise ^ 0x33u;
    dst->value = src->public_value;
}

void alias_value(volatile struct output *dst, const struct input *src, int select) {
    const uint32_t *chosen = &src->public_value;
    if (select > 0) chosen = &src->secret;
    dst->value = *chosen;
}

void transform_value(volatile struct output *dst, const struct input *src, int select) {
    dst->value = (src->secret ^ 0x55u) + src->public_value;
}
