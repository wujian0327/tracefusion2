#include <signal.h>
#include <stdio.h>
#include <string.h>
#include "model.h"

/* Oracle lives only in this harness, never in the operations or inference. */
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--wait")) raise(SIGSTOP);
    const operation functions[] = {choose_value, overwrite_value, alias_value, transform_value};
    const char *names[] = {"choose_value", "overwrite_value", "alias_value", "transform_value"};
    unsigned sequence = 0;
    for (unsigned round = 0; round < 2; ++round) {
        struct input src = {424242u + round, 424242u + round, 99u};
        for (unsigned f = 0; f < 4; ++f) {
            for (int select = 0; select < 2; ++select) {
                struct output dst = {0xdeadbeefu, 0};
                functions[f](&dst, &src, select);
                const char *origins = f == 3 ? "\"input.secret\",\"input.public_value\"" :
                    ((f == 0 || f == 2) && select > 0 ? "\"input.secret\"" : "\"input.public_value\"");
                uint32_t expected = f == 3 ? (src.secret ^ 0x55u) + src.public_value :
                    ((f == 0 || f == 2) && select > 0 ? src.secret : src.public_value);
                printf("{\"sequence\":%u,\"function\":\"%s\",\"select\":%d,"
                       "\"expected_sources\":[%s],\"expected_value\":%u,\"output\":%u}\n",
                       ++sequence, names[f], select, origins, expected, dst.value);
            }
        }
    }
    return 0;
}
