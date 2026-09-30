#include <stdint.h>

struct input { uint32_t secret; uint32_t public_value; };
struct output { uint32_t value; };

void copy_secret(struct output *, const struct input *);
void copy_public(struct output *, const struct input *);
void transform_secret(struct output *, const struct input *);
