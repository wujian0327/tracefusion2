#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <errno.h>

/* Fork AFTER exec into this small image: do not inherit Python's analysis heap. */
int main(int argc, char **argv) {
    if (argc < 3) return 64;
    long total = 0, resident = -1;
    FILE *statm = fopen("/proc/self/statm", "r");
    if (statm) {
        if (fscanf(statm, "%ld %ld", &total, &resident) != 2) resident = -1;
        fclose(statm);
    }
    pid_t pid = fork();
    if (pid < 0) return 71;
    if (!pid) { execvp(argv[2], argv + 2); perror("execvp"); _exit(127); }
    int status;
    struct rusage usage;
    while (wait4(pid, &status, 0, &usage) < 0) if (errno != EINTR) return 72;
    FILE *out = fopen(argv[1], "w");
    if (!out) return 73;
    fprintf(out, "%.9f %.9f %ld %ld\n",
        usage.ru_utime.tv_sec + usage.ru_utime.tv_usec / 1e6,
        usage.ru_stime.tv_sec + usage.ru_stime.tv_usec / 1e6,
        usage.ru_maxrss, resident < 0 ? -1 : resident * (sysconf(_SC_PAGESIZE) / 1024));
    if (fclose(out)) return 74;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
