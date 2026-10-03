#define _XOPEN_SOURCE 700
#include "model.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Explicit serialization contract. Probes observe entry/return; snprintf
 * internals are modeled by json-u32-value-v1, not instruction-replayed. */
int format_json(char *buffer, const uint32_t *value) {
    return snprintf(buffer, 32, "{\"value\":%u}\n", (unsigned)*value);
}

/* Evaluation-only records. The collector/inference never reads these. */
struct answer {
    const char *function, *fields, *file;
    unsigned sequence, reads, id, second_id, offset, count;
    uint32_t expected, output;
};
struct write_answer { unsigned format, call; int fd; };
static struct answer answers[32];
static struct write_answer writes[32];
static unsigned ncalls, nformats, nwrites;
static void die(const char *where) { perror(where); exit(1); }
static void answer(const char *function, const char *fields, uint32_t expected,
                   uint32_t output, unsigned reads, unsigned id, const char *file,
                   unsigned offset, unsigned count, unsigned second_id) {
    answers[ncalls]=(struct answer){function,fields,file,ncalls+1,reads,id,second_id,offset,count,expected,output};
    ncalls++;
}
static void read_checked(int fd, uint32_t *dst, off_t off, ssize_t expected) {
    ssize_t n=pread(fd,dst,4,off);
    if(n!=expected || (expected<0 && errno!=EBADF)) die("pread result");
}
static int serialize(char *buffer, const struct output *dst) {
    int n=format_json(buffer,&dst->value); ++nformats;
    if(n<0 || n>=32) die("format_json");
    return n;
}
static void send_json(int fd, char *buffer, int n) {
    ssize_t result=write(fd,buffer,(size_t)n);
    if((fd==1 && result!=n) || (fd==-1 && (result!=-1 || errno!=EBADF))) die("write result");
    writes[nwrites++]=(struct write_answer){nformats,ncalls,fd};
}

void run_workload(int a, int b) {
    struct input src={0,0,99}; struct output dst={0,0}; char buffer[32];
    unsigned reads=0;
    for(unsigned round=0;round<2;++round) {
        off_t off=round*4; uint32_t v=424242u+round;
        for(unsigned c=0;c<9;++c) {
            unsigned first=reads+1,id=first,count=1,offset=(unsigned)off;
            const char *file="a.bin",*function="select_value",*fields="[\"input.left\"]";
            uint32_t expected=(v^0x55u)+3u;
            if(c<=2) {
                read_checked(a,&src.left,off,4); read_checked(b,&src.right,off,4); reads+=2;
                if(c==0) select_value(&dst,&src,1);
                if(c==1) {select_value(&dst,&src,0); expected=v;id++;file="b.bin";fields="[\"input.right\"]";}
                if(c==2) {merge_values(&dst,&src,0);expected+=v;function="merge_values";count=2;fields="[\"input.left\",\"input.right\"]";}
            } else if(c==7) {
                read_checked(-1,&src.left,off,-1);reads++;
                fallback_value(&dst,&src,0);expected=42;function="fallback_value";count=0;fields="[]";
            } else {
                read_checked(a,&src.left,off,4);reads++;
                if(c==3) {read_checked(b,&src.left,off,4);id++;file="b.bin";}
                if(c==4) {read_checked(a,&src.left,(1-round)*4,4);id++;offset=(1-round)*4;expected=((424243u-round)^0x55u)+3u;}
                if(c==5) read_checked(-1,&src.left,off,-1);
                if(c==6) read_checked(b,&src.left,16,0);
                if(c==8) {read_checked(a,&src.left,off,4);id++;}
                reads++; select_value(&dst,&src,1);
            }
            answer(function,fields,expected,dst.value,reads,id,file,offset,count,first+1);
            int n=serialize(buffer,&dst);send_json(1,buffer,n);
        }
    }
    /* Compute sensitive data, overwrite it with a constant, then serialize. */
    read_checked(a,&src.left,0,4);read_checked(b,&src.right,0,4);reads+=2;
    select_value(&dst,&src,1);
    answer("select_value","[\"input.left\"]",424298,dst.value,reads,reads-1,"a.bin",0,1,0);
    fallback_value(&dst,&src,0);
    answer("fallback_value","[]",42,dst.value,reads,0,"a.bin",0,0,0);
    int n=serialize(buffer,&dst);send_json(1,buffer,n);
    /* Same JSON bytes, distinct source versions: only the second is written. */
    read_checked(a,&src.left,0,4);read_checked(b,&src.right,0,4);reads+=2;
    copy_left(&dst,&src,0);
    answer("copy_left","[\"input.left\"]",424242,dst.value,reads,reads-1,"a.bin",0,1,0);
    (void)serialize(buffer,&dst);
    select_value(&dst,&src,0);
    answer("select_value","[\"input.right\"]",424242,dst.value,reads,reads,"b.bin",0,1,0);
    n=serialize(buffer,&dst);send_json(1,buffer,n);
    /* A failed write has a buffer provenance but no emitted-field relation. */
    read_checked(a,&src.left,0,4);read_checked(b,&src.right,0,4);reads+=2;
    select_value(&dst,&src,1);
    answer("select_value","[\"input.left\"]",424298,dst.value,reads,reads-1,"a.bin",0,1,0);
    n=serialize(buffer,&dst);send_json(-1,buffer,n);
    /* Numeric boundaries exercise variable decimal width and unsignedness. */
    for(unsigned k=0;k<2;++k) {
        read_checked(b,&src.right,8+4*k,4);reads++;
        select_value(&dst,&src,0);
        answer("select_value","[\"input.right\"]",k?UINT32_MAX:0,dst.value,reads,reads,"b.bin",8+4*k,1,0);
        n=serialize(buffer,&dst);send_json(1,buffer,n);
    }
}

static void print_oracle(void) {
    fputs("{\"computations\":[",stderr);
    for(unsigned i=0;i<ncalls;++i) {
        struct answer *r=&answers[i];
        fprintf(stderr,"%s{\"sequence\":%u,\"function\":\"%s\",\"expected_sources\":%s,\"expected_value\":%u,\"output\":%u,\"expected_read_attempts\":%u,\"expected_external_sources\":[",i?",":"",r->sequence,r->function,r->fields,r->expected,r->output,r->reads);
        if(r->count) fprintf(stderr,"{\"io_id\":%u,\"file_name\":\"%s\",\"file_offset\":%u,\"length\":4}",r->id,r->file,r->offset);
        if(r->count==2) fprintf(stderr,",{\"io_id\":%u,\"file_name\":\"b.bin\",\"file_offset\":%u,\"length\":4}",r->second_id,r->offset);
        fputs("]}",stderr);
    }
    fprintf(stderr,"],\"format_count\":%u,\"writes\":[",nformats);
    for(unsigned i=0;i<nwrites;++i) fprintf(stderr,"%s{\"write_id\":%u,\"format_id\":%u,\"call_id\":%u,\"fd\":%d}",i?",":"",i+1,writes[i].format,writes[i].call,writes[i].fd);
    fputs("]}\n",stderr);
}
int main(int argc,char **argv) {
    char dir[512],paths[2][544];const char *tmp=getenv("TMPDIR");
    if(snprintf(dir,sizeof(dir),"%s/tracefusion-json-XXXXXX",tmp?tmp:".")>=sizeof(dir)) return 1;
    if(!mkdtemp(dir)) die("mkdtemp");
    int fds[2]; uint32_t values[]={424242,424243,0,UINT32_MAX};
    for(int i=0;i<2;++i) {
        snprintf(paths[i],sizeof(paths[i]),"%s/%c.bin",dir,'a'+i);
        int fd=open(paths[i],O_WRONLY|O_CREAT|O_EXCL,0600);
        if(fd<0 || write(fd,values,sizeof(values))!=sizeof(values) || close(fd)) die("fixture write");
        fds[i]=open(paths[i],O_RDONLY);if(fds[i]<0) die("fixture open");
    }
    if(argc==2 && strcmp(argv[1],"--wait")==0) raise(SIGSTOP);
    run_workload(fds[0],fds[1]);
    for(int i=0;i<2;++i) {close(fds[i]);unlink(paths[i]);}rmdir(dir);
    print_oracle();return 0;
}
