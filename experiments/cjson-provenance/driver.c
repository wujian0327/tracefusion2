/* Only workload invocation, boundary markers and output recording.
 * The parser, field access, replacement and serializer are upstream cJSON. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
struct test_case {
    const char *name, *text, *replace_key, *replacement;
    unsigned query_count;
    const char *paths[4];
};
#include "cases.h"

__attribute__((noinline)) void tf_cjson_begin(const char *input, size_t size, const char *replacement) {
    __asm__ volatile("" : : "r"(input), "r"(size), "r"(replacement) : "memory");
}
__attribute__((noinline)) void tf_cjson_sink(cJSON *root, cJSON *field, unsigned query) {
    __asm__ volatile("" : : "r"(root), "r"(field), "r"(query) : "memory");
}
static void hex(const char *s) {
    if (s) for (; *s; ++s) printf("%02x", (unsigned char)*s);
}
static cJSON *lookup(cJSON *root, const char *path) {
    char copy[128];
    if (strlen(path)>=sizeof(copy) || path[0]!='/') return NULL;
    strcpy(copy,path+1);
    cJSON *node=root;
    for (char *key=strtok(copy,"/"); key && node; key=strtok(NULL,"/")) {
        if (cJSON_IsArray(node)) node=cJSON_GetArrayItem(node,atoi(key));
        else if (cJSON_IsObject(node)) node=cJSON_GetObjectItemCaseSensitive(node,key);
        else return NULL;
    }
    return node;
}
int main(void) {
    for (unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        const struct test_case *t=&cases[i];
        size_t n=strlen(t->text)+1;
        tf_cjson_begin(t->text,n,t->replacement);
        cJSON *root=cJSON_ParseWithLengthOpts(t->text,n,NULL,1);
        if (root && t->replace_key) {
            cJSON *replacement=cJSON_CreateString(t->replacement);
            if (!replacement) return 2;
            if (!cJSON_ReplaceItemInObjectCaseSensitive(root,t->replace_key,replacement)) {
                cJSON_Delete(replacement); cJSON_Delete(root); return 3;
            }
        }
        printf("{\"case\":\"%s\",\"parsed\":%s,\"queries\":[",t->name,root?"true":"false");
        for (unsigned q=0;q<t->query_count;++q) {
            cJSON *field=root?lookup(root,t->paths[q]):NULL;
            tf_cjson_sink(root,field,q);
            if (q) putchar(',');
            printf("{\"path\":\"%s\",\"status\":\"%s\"",t->paths[q],cJSON_IsString(field)?"string":"no_sink");
            if (cJSON_IsString(field)) { printf(",\"value_hex\":\""); hex(cJSON_GetStringValue(field)); putchar('"'); }
            putchar('}');
        }
        printf("],\"serialized_hex\":");
        if (root) {
            char output[4096];
            if (!cJSON_PrintPreallocated(root,output,sizeof(output),0)) { cJSON_Delete(root); return 4; }
            putchar('"'); hex(output); putchar('"');
        } else printf("null");
        printf("}\n");
        cJSON_Delete(root);
    }
    return 0;
}
