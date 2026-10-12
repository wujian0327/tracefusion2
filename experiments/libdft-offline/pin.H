// Type-only compatibility header. No Pin instrumentation or execution emulation.
#pragma once
#include <cstdint>
#include <cstddef>
#include <sstream>
#include <iostream>
using ADDRINT = uintptr_t;
using THREADID = uint32_t;
using UINT32 = uint32_t;
using INS = void*;
#define PIN_FAST_ANALYSIS_CALL
#define LOG(message) do { std::cerr << (message); } while (0)
