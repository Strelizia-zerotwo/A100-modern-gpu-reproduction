#include <cuda_runtime.h>
#include <stdint.h>

extern "C" __global__
void cggty_probe(uint32_t* start_clock,
                 uint32_t* stop_clock,
                 uint32_t* hardware_warp_id,
                 uint32_t* sink)
{
    const uint32_t lane = threadIdx.x & 31u;
    const uint32_t logical_warp = threadIdx.x >> 5;

    uint32_t hw_warp;
    uint32_t start;
    uint32_t stop;

    asm volatile(
        "mov.u32 %0, %%warpid;\n\t"
        : "=r"(hw_warp)
    );

    asm volatile(
        "mov.u32 %0, %%clock;\n\t"
        : "=r"(start)
        :
        : "memory"
    );

    // 占位指令 1：后续改成目标 NOP。
    asm volatile(
        "bar.sync 0;\n\t"
        :
        :
        : "memory"
    );

    // 占位指令 2：后续改成固定 spacer NOP。
    asm volatile(
        "bar.sync 0;\n\t"
        :
        :
        : "memory"
    );

    asm volatile(
        "mov.u32 %0, %%clock;\n\t"
        : "=r"(stop)
        :
        : "memory"
    );

    if (lane == 0) {
        start_clock[logical_warp] = start;
        stop_clock[logical_warp] = stop;
        hardware_warp_id[logical_warp] = hw_warp;
        sink[logical_warp] = start ^ stop ^ hw_warp;
    }
}
