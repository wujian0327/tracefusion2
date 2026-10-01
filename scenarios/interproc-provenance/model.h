#include <stdint.h>
struct input { uint32_t secret, public_value, noise; };
struct output { uint32_t value, audit; };
typedef void (*operation)(volatile struct output *, const struct input *, int);
void pipeline_branch(volatile struct output *, const struct input *, int);
void pipeline_repeat(volatile struct output *, const struct input *, int);
void pipeline_merge(volatile struct output *, const struct input *, int);
