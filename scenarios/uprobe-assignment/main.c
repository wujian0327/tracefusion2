#include <signal.h>
#include <stdio.h>
#include <string.h>
#include "model.h"

/* The harness pauses before business operations so external probes can attach.
 * stdout is an independent evaluation oracle; the collector does not read it. */
int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--wait") == 0) raise(SIGSTOP);
    void (*functions[])(struct output *, const struct input *) = {
        copy_secret, copy_public, transform_secret};
    const char *names[] = {"copy_secret", "copy_public", "transform_secret"};
    const char *fields[] = {"secret", "public_value", "secret"};
    for (unsigned round = 0; round < 2; round++) {
        struct input src = {424242u + round, 424242u + round};
        for (unsigned i = 0; i < 3; i++) {
            struct output dst = {0xdeadbeefu};
            functions[i](&dst, &src);
            printf("{\"sequence\":%u,\"function\":\"%s\",\"expected_field\":\"%s\","
                   "\"secret\":%u,\"public_value\":%u,\"output\":%u}\n",
                   round * 3 + i + 1, names[i], fields[i], src.secret, src.public_value, dst.value);
        }
    }
    return 0;
}
