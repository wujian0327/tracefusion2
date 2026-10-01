#include "model.h"

void loop_transform(volatile struct output *dst, const volatile struct input *src, int count) {
    uint32_t x = src->secret;
    for (int i = 0; i < count; ++i) x = (x ^ 0x55u) + 3u;
    dst->value = x;
}

void loop_overwrite(volatile struct output *dst, const volatile struct input *src, int count) {
    uint32_t x = 42u;
    for (int i = 0; i < count; ++i) {
        if (i < 2) x = src->secret;
        else x = src->public_value;
    }
    dst->value = x;
}

void loop_accumulate(volatile struct output *dst, const volatile struct input *src, int count) {
    uint32_t x = 0u;
    for (int i = 0; i < count; ++i) {
        if (i < 2) x += src->secret;
        else x += src->public_value;
    }
    dst->value = x;
}
