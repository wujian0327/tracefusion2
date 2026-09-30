#include "model.h"

/* Ordinary assignments: no tracing calls, taint tags, asm markers or USDT. */
void copy_secret(struct output *dst, const struct input *src) {
    dst->value = src->secret;
}

void copy_public(struct output *dst, const struct input *src) {
    dst->value = src->public_value;
}

void transform_secret(struct output *dst, const struct input *src) {
    dst->value = src->secret ^ 0x55u;
}
