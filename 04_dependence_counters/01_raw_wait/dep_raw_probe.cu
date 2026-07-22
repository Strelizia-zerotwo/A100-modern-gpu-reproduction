#include <cuda_runtime.h>
#include <stdint.h>

extern "C" __global__
void dep_raw_probe(const uint32_t* input,
                   uint32_t* start_clock,
                   uint32_t* stop_clock,
                   uint32_t* output)
{
    const uint32_t index = threadIdx.x;
    const uint32_t* address = input + index;

    uint32_t start;
    uint32_t stop;
    uint32_t result;

    asm volatile(
        "mov.u32 %0, %%clock;\n\t"
        "ld.global.u32 %2, [%3];\n\t"
        "add.u32 %2, %2, 1;\n\t"
        "bar.sync 0;\n\t"
        "mov.u32 %1, %%clock;\n\t"
        : "=r"(start),
          "=r"(stop),
          "=r"(result)
        : "l"(address)
        : "memory"
    );

    start_clock[index] = start;
    stop_clock[index] = stop;
    output[index] = result;
}
