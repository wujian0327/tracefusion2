#include <signal.h>
#include <stdio.h>
#include <string.h>
#include "model.h"

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--wait")) raise(SIGSTOP);
    operation functions[] = {loop_call_overwrite, loop_call_accumulate, loop_call_transform};
    const char *names[] = {"loop_call_overwrite", "loop_call_accumulate", "loop_call_transform"};
    const uint32_t counts[] = {0, 1, 2, 4};
    unsigned sequence = 0;
    for (unsigned round = 0; round < 2; ++round) {
        struct input src = {424242u + round, 424242u + round, 99u};
        for (unsigned f = 0; f < 3; ++f) {
            for (unsigned c = 0; c < sizeof(counts)/sizeof(counts[0]); ++c) {
                uint32_t count = counts[c], secret_count = count < 2 ? count : 2;
                struct output dst = {0xdeadbeefu, 0};
                functions[f](&dst, &src, count);
                /* Independent workload truth; never reads a plan or event. */
                uint32_t expected = f == 0 ? (count == 0 ? 42u : count <= 2 ? src.secret : src.public_value) :
                    f == 1 ? secret_count * src.secret + (count-secret_count) * src.public_value :
                    secret_count * (src.secret ^ 0x55u) + (count-secret_count) * (src.public_value ^ 0x55u);
                const char *fields = count == 0 ? "" : f == 0 ? (count <= 2 ? "\"input.secret\"" : "\"input.public_value\"") :
                    count <= 2 ? "\"input.secret\"" : "\"input.secret\",\"input.public_value\"";
                printf("{\"sequence\":%u,\"function\":\"%s\",\"count\":%u,\"expected_helper_calls\":%u,"
                       "\"expected_sources\":[%s],\"expected_value\":%u,\"output\":%u}\n",
                       ++sequence, names[f], count, count * (f == 2 ? 2u : 1u), fields, expected, dst.value);
            }
        }
    }
    return 0;
}
