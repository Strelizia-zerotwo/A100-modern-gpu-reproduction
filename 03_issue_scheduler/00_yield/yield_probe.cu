#include <cuda_runtime.h>
#include <cstdint>

extern "C" __global__
void yield_probe(std::uint32_t* start_clock,
                 std::uint32_t* stop_clock,
                 std::uint32_t* sink)
{
    if (blockIdx.x != 0) {
        return;
    }

    std::uint32_t start;
    std::uint32_t stop;
    std::uint32_t target_value;
    std::uint32_t spacer_value;

    asm volatile(
        "mov.u32 %0, %%clock;\n\t"
        : "=r"(start)
        :
        : "memory"
    );

    // 目标指令：后续只修改这条指令的 Yield/Stall 控制字段。
    asm volatile(
        "mov.u32 %0, 1;\n\t"
        : "=r"(target_value)
        :
        : "memory"
    );

    // 固定 spacer：所有变体保持完全相同。
    asm volatile(
        "mov.u32 %0, 2;\n\t"
        : "=r"(spacer_value)
        :
        : "memory"
    );

    asm volatile(
        "mov.u32 %0, %%clock;\n\t"
        : "=r"(stop)
        :
        : "memory"
    );

    if (threadIdx.x == 0) {
        *start_clock = start;
        *stop_clock = stop;

        // 使用两个 MOV 的结果，防止编译器将它们视为无用值。
        *sink = start ^ stop ^ target_value ^ spacer_value;
    }
}
