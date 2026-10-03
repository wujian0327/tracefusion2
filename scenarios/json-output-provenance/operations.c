#include "model.h"
static uint32_t transform_left(const struct input *src) { return (src->left ^ 0x55u) + 3u; }
static uint32_t read_right(const struct input *src) { return src->right; }
void select_value(struct output *dst, const struct input *src, uint32_t select) {
    if (select) dst->value = transform_left(src);
    else dst->value = read_right(src);
}
void merge_values(struct output *dst, const struct input *src, uint32_t unused) {
    (void)unused;
    uint32_t left = transform_left(src);
    dst->value = left + read_right(src);
}
void fallback_value(struct output *dst, const struct input *src, uint32_t unused) {
    (void)src; (void)unused; dst->value = 42;
}

void copy_left(struct output *dst, const struct input *src, uint32_t unused) {
    (void)unused; dst->value = src->left;
}
