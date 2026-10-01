#include <signal.h>
#include <stdio.h>
#include <string.h>
#include "model.h"

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--wait")) raise(SIGSTOP);
    operation functions[] = {loop_transform, loop_overwrite, loop_accumulate};
    const char *names[] = {"loop_transform", "loop_overwrite", "loop_accumulate"};
    const int counts[] = {0, 1, 2, 4};
    unsigned sequence = 0;
    for (unsigned round = 0; round < 2; ++round) {
        struct input src = {424242u + round, 424242u + round, 99u};
        for (unsigned f = 0; f < 3; ++f) {
            for (unsigned c = 0; c < sizeof(counts)/sizeof(counts[0]); ++c) {
                int count = counts[c];
                struct output dst = {0xdeadbeefu, 0};
                functions[f](&dst, &src, count);
                uint32_t expected = f == 0 ? src.secret : f == 1 ? 42u : 0u;
                if (f == 0) for (int i = 0; i < count; ++i) expected = (expected ^ 0x55u) + 3u;
                if (f == 1 && count > 0) expected = count <= 2 ? src.secret : src.public_value;
                if (f == 2) expected = (count < 2 ? count : 2) * src.secret + (count > 2 ? count-2 : 0) * src.public_value;
                const char *fields = f == 0 ? "\"input.secret\"" : count == 0 ? "" :
                    f == 1 ? (count <= 2 ? "\"input.secret\"" : "\"input.public_value\"") :
                    count <= 2 ? "\"input.secret\"" : "\"input.secret\",\"input.public_value\"";
                printf("{\"sequence\":%u,\"function\":\"%s\",\"count\":%d,\"expected_sources\":[%s],"
                       "\"expected_value\":%u,\"output\":%u,\"expected_read_instances\":[",
                       ++sequence, names[f], count, fields, expected, dst.value);
                /* Oracle uses workload semantics only, never the generated plan. */
                if (f == 0) printf("\"input.secret@read1\"");
                else if (f == 1 && count > 0) printf("\"input.%s@read%d\"", count <= 2 ? "secret" : "public_value", count);
                else if (f == 2) for (int i = 0; i < count; ++i)
                    printf("%s\"input.%s@read%d\"", i ? "," : "", i < 2 ? "secret" : "public_value", i+1);
                printf("]}\n");
            }
        }
    }
    return 0;
}
