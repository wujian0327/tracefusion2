#include <stdint.h>
struct input { uint32_t left, right, noise; };
struct output { uint32_t value, audit; };
void select_value(struct output *, const struct input *, uint32_t);
void merge_values(struct output *, const struct input *, uint32_t);
void fallback_value(struct output *, const struct input *, uint32_t);
void copy_left(struct output *, const struct input *, uint32_t);
