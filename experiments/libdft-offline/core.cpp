// Offline transport only. Propagation callbacks, BDD labels and tagmap are upstream.
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "libdft_api.h"

static thread_ctx_t context{};
thread_ctx_t *threads_ctx = &context;
void libdft_die() { throw std::runtime_error("upstream allocation failure"); }
static void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
static bool reg_ok(uint64_t x) { return x >= DFT_REG_RDI && x <= DFT_REG_R15; }
static bool addr_ok(uint64_t x) { return x > 0 && x <= 0x7fffffffffffULL - 32; }
#include "callbacks.inc"

static void labels(tag_t t) {
    std::set<unsigned> out;
    for (auto s: tag_get(t)) {
        require(s.end >= s.begin && s.end <= 4096, "label range");
        for (auto i=s.begin; i<s.end; ++i) out.insert(i);
    }
    std::cout << '[';
    bool first=true;
    for (auto x: out) { if (!first) std::cout << ','; first=false; std::cout << x; }
    std::cout << ']';
}
int main() {
    try {
        std::string line;
        size_t commands=0;
        bool complete=false;
        while (std::getline(std::cin,line)) {
            require(!complete && ++commands <= 200000, "command limit or data after end");
            std::istringstream in(line);
            std::string op; in >> op;
            if (op=="call") {
                std::string name; in >> name;
                std::vector<uint64_t> a; uint64_t v;
                while (in >> v) a.push_back(v);
                require(in.eof(), "bad callback number");
                dispatch(name,a);
            } else if (op=="seed") {
                uint64_t addr=0,n=0,label=0; in >> addr >> n >> label;
                require(bool(in) && addr_ok(addr) && n>0 && n<=32 && label>0 && label<4096, "seed operands");
                std::string extra; require(!(in>>extra), "extra seed operands");
                tagmap_setn(addr,n,tag_alloc<tag_t>(label));
            } else if (op=="clear") {
                uint64_t addr=0,n=0; in >> addr >> n;
                require(bool(in) && addr_ok(addr) && n>0 && n<=32, "clear operands");
                std::string extra; require(!(in>>extra), "extra clear operands");
                tagmap_clrn(addr,n);
            } else if (op=="memory" || op=="register") {
                uint64_t where=0,n=0; in >> where >> n;
                require(bool(in) && n>0 && n<=32 && (op=="memory" ? addr_ok(where) : reg_ok(where)), "query operands");
                std::string extra; require(!(in>>extra), "extra query operands");
                std::cout << "{\"kind\":\"" << op << "\",\"location\":" << where << ",\"bytes\":[";
                for (size_t i=0;i<n;++i) {
                    if (i) std::cout << ',';
                    labels(op=="memory" ? tagmap_getb(where+i) : tagmap_getb_reg(0,where,i));
                }
                std::cout << "]}\n";
            } else if (op=="end") {
                std::string extra; require(!(in>>extra), "extra end operands");
                complete=true;
            } else throw std::runtime_error("unknown command: " + op);
        }
        require(complete,"missing end");
        std::cout << "{\"status\":\"complete\",\"commands\":" << commands << "}\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr << "unknown: " << e.what() << '\n';
        return 2;
    }
}
