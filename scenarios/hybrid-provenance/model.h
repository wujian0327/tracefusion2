#include <stdint.h>

struct input { uint32_t secret, public_value, noise; };
struct output { uint32_t value, audit; };
typedef void (*operation)(volatile struct output *, const struct input *, int);
void choose_value(volatile struct output *, const struct input *, int);
void overwrite_value(volatile struct output *, const struct input *, int);
void alias_value(volatile struct output *, const struct input *, int);
void transform_value(volatile struct output *, const struct input *, int);
