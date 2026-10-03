#include <stdint.h>
struct input { uint32_t secret, public_value, noise; };
struct output { uint32_t value, audit; };
typedef void (*operation)(volatile struct output *, const volatile struct input *, uint32_t);
void loop_call_overwrite(volatile struct output *, const volatile struct input *, uint32_t);
void loop_call_accumulate(volatile struct output *, const volatile struct input *, uint32_t);
void loop_call_transform(volatile struct output *, const volatile struct input *, uint32_t);
