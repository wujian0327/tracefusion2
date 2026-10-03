#include "model.h"

static uint32_t read_iteration(const volatile struct input *src, uint32_t i) {
    if (i < 2u) return src->secret;
    return src->public_value;
}

static uint32_t transform_iteration(const volatile struct input *src, uint32_t i) {
    return read_iteration(src, i) ^ 0x55u;
}

void loop_call_overwrite(volatile struct output *dst, const volatile struct input *src, uint32_t count) {
    uint32_t x = 42u;
    for (uint32_t i = 0; i < count; ++i) x = read_iteration(src, i);
    dst->value = x;
}

void loop_call_accumulate(volatile struct output *dst, const volatile struct input *src, uint32_t count) {
    uint32_t x = 0u;
    for (uint32_t i = 0; i < count; ++i) x += read_iteration(src, i);
    dst->value = x;
}

void loop_call_transform(volatile struct output *dst, const volatile struct input *src, uint32_t count) {
    uint32_t x = 0u;
    for (uint32_t i = 0; i < count; ++i) x += transform_iteration(src, i);
    dst->value = x;
}
