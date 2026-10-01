#include <signal.h>
#include <stdio.h>
#include <string.h>
#include "model.h"

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--wait")) raise(SIGSTOP);
    operation functions[] = {pipeline_branch, pipeline_repeat, pipeline_merge};
    const char *names[] = {"pipeline_branch", "pipeline_repeat", "pipeline_merge"};
    unsigned sequence = 0;
    for (unsigned round = 0; round < 2; ++round) {
        struct input src = {424242u + round, 424242u + round, 99u};
        for (unsigned f = 0; f < 3; ++f) {
            for (int select = 0; select < 2; ++select) {
                struct output dst = {0xdeadbeefu, 0};
                functions[f](&dst, &src, select);
                uint32_t selected = select > 0 ? src.secret : src.public_value;
                uint32_t expected = f == 0 ? selected ^ 0x55u :
                    f == 1 ? src.public_value : (selected ^ 0x55u) + src.public_value;
                const char *origins = f == 1 || select == 0 ? "\"input.public_value\"" :
                    f == 0 ? "\"input.secret\"" : "\"input.secret\",\"input.public_value\"";
                printf("{\"sequence\":%u,\"function\":\"%s\",\"select\":%d,"
                       "\"expected_sources\":[%s],\"expected_value\":%u,\"output\":%u}\n",
                       ++sequence, names[f], select, origins, expected, dst.value);
            }
        }
    }
    return 0;
}
