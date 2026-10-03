#define _XOPEN_SOURCE 700
#include "model.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void die(const char *where) { perror(where); exit(1); }
static void read_checked(int fd, uint32_t *dst, off_t off, ssize_t expected) {
    ssize_t n = pread(fd, dst, sizeof(*dst), off);
    if (n != expected || (expected < 0 && errno != EBADF)) die("pread result");
}
/* Ordinary workload driver: no trace IDs, source tags or probe calls. Only
 * pread writes the input buffer during this scope. JSON below is test truth. */
void run_workload(int a, int b) {
    struct input src = {0, 0, 99};
    unsigned sequence = 0, reads = 0;
    for (unsigned round = 0; round < 2; ++round) {
        off_t off = round * 4;
        uint32_t v = 424242u + round;
        for (unsigned c = 0; c < 9; ++c) {
            struct output dst = {0xdeadbeef, 0};
            unsigned first = reads + 1, expected_id = first;
            const char *file = "a.bin", *name = "select_value", *fields = "[\"input.left\"]";
            unsigned source_count = 1, source_offset = (unsigned)off;
            uint32_t expected = (v ^ 0x55u) + 3u;
            if (c <= 2) {
                read_checked(a, &src.left, off, 4); read_checked(b, &src.right, off, 4); reads += 2;
                if (c == 0) select_value(&dst, &src, 1);
                if (c == 1) { select_value(&dst, &src, 0); expected = v; expected_id++; file = "b.bin"; fields = "[\"input.right\"]"; }
                if (c == 2) { merge_values(&dst, &src, 0); expected += v; name = "merge_values"; source_count = 2; fields = "[\"input.left\",\"input.right\"]"; }
            } else if (c == 7) {
                read_checked(-1, &src.left, off, -1); reads++;
                fallback_value(&dst, &src, 0); expected = 42; name = "fallback_value"; source_count = 0; fields = "[]";
            } else {
                read_checked(a, &src.left, off, 4); reads++;
                if (c == 3) { read_checked(b, &src.left, off, 4); expected_id++; file = "b.bin"; }
                if (c == 4) { read_checked(a, &src.left, (1-round)*4, 4); expected_id++; source_offset = (1-round)*4; expected = ((424243u-round)^0x55u)+3u; }
                if (c == 5) read_checked(-1, &src.left, off, -1);
                if (c == 6) read_checked(b, &src.left, 8, 0);
                if (c == 8) { read_checked(a, &src.left, off, 4); expected_id++; }
                reads++;
                select_value(&dst, &src, 1);
            }
            printf("{\"sequence\":%u,\"case\":%u,\"round\":%u,\"function\":\"%s\",\"expected_sources\":%s,\"expected_value\":%u,\"output\":%u,\"expected_read_attempts\":%u,\"expected_external_sources\":[", ++sequence,c,round,name,fields,expected,dst.value,reads);
            if (source_count) printf("{\"io_id\":%u,\"file_name\":\"%s\",\"file_offset\":%u,\"length\":4}",expected_id,file,source_offset);
            if (source_count == 2) printf(", {\"io_id\":%u,\"file_name\":\"b.bin\",\"file_offset\":%u,\"length\":4}",first+1,(unsigned)off);
            puts("]}");
        }
    }
}
int main(int argc, char **argv) {
    char dir[512], paths[2][544];
    const char *tmp = getenv("TMPDIR");
    if (snprintf(dir, sizeof(dir), "%s/tracefusion-read-XXXXXX", tmp ? tmp : ".") >= sizeof(dir)) return 1;
    int fds[2]; uint32_t values[] = {424242, 424243};
    if (!mkdtemp(dir)) die("mkdtemp");
    for (int i = 0; i < 2; ++i) {
        snprintf(paths[i], sizeof(paths[i]), "%s/%c.bin", dir, 'a'+i);
        int fd = open(paths[i], O_WRONLY|O_CREAT|O_EXCL, 0600);
        if (fd < 0 || write(fd, values, sizeof(values)) != sizeof(values) || close(fd)) die("fixture write");
        fds[i] = open(paths[i], O_RDONLY);
        if (fds[i] < 0) die("fixture open");
    }
    if (argc == 2 && strcmp(argv[1], "--wait") == 0) raise(SIGSTOP);
    run_workload(fds[0], fds[1]);
    for (int i = 0; i < 2; ++i) { close(fds[i]); unlink(paths[i]); }
    rmdir(dir);
    return 0;
}
