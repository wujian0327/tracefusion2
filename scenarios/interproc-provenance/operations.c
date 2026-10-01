#include "model.h"

/* Direct ordinary C calls; helpers are discovered from the binary call targets. */
uint32_t read_secret(const struct input *src) { return src->secret; }
uint32_t read_public(const struct input *src) { return src->public_value; }
uint32_t read_selected(const struct input *src, int select) {
    if (select > 0) return read_secret(src);
    return read_public(src);
}
uint32_t encode_value(uint32_t value) { return value ^ 0x55u; }
uint32_t combine_values(uint32_t first, uint32_t second) { return (first ^ 0x55u) + second; }
void store_value(volatile struct output *dst, uint32_t value) { dst->value = value; }

void pipeline_branch(volatile struct output *dst, const struct input *src, int select) {
    /* Keep a real stack spill/reload in this controlled compilation. */
    volatile uint32_t staged = read_selected(src, select);
    store_value(dst, encode_value(staged));
}
void pipeline_repeat(volatile struct output *dst, const struct input *src, int select) {
    store_value(dst, read_selected(src, 1));
    store_value(dst, read_selected(src, 0));
}
void pipeline_merge(volatile struct output *dst, const struct input *src, int select) {
    uint32_t first = read_selected(src, select);
    uint32_t second = read_public(src);
    store_value(dst, combine_values(first, second));
}
