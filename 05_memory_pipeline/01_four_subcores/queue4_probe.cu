#include <cuda_runtime.h>
#include <stdint.h>

extern "C" __global__
void queue_probe(const uint32_t* input,
                 uint32_t* start_clock,
                 uint32_t* stop_clock,
                 uint32_t* output)
{
    __shared__ uint32_t shared_data[128];

    const uint32_t index = threadIdx.x;

    shared_data[index] = input[index];
    __syncthreads();

    const uint32_t shared_address =
        static_cast<uint32_t>(
            __cvta_generic_to_shared(&shared_data[index])
        );

    uint32_t start;
    uint32_t stop;

    uint32_t value0;
    uint32_t value1;
    uint32_t value2;
    uint32_t value3;
    uint32_t value4;
    uint32_t value5;
    uint32_t value6;
    uint32_t value7;
    uint32_t value8;
    uint32_t value9;

    asm volatile(
        "mov.u32 %0, %%clock;\n\t"

        "ld.shared.volatile.u32 %2,  [%12];\n\t"
        "ld.shared.volatile.u32 %3,  [%12];\n\t"
        "ld.shared.volatile.u32 %4,  [%12];\n\t"
        "ld.shared.volatile.u32 %5,  [%12];\n\t"
        "ld.shared.volatile.u32 %6,  [%12];\n\t"
        "ld.shared.volatile.u32 %7,  [%12];\n\t"
        "ld.shared.volatile.u32 %8,  [%12];\n\t"
        "ld.shared.volatile.u32 %9,  [%12];\n\t"
        "ld.shared.volatile.u32 %10, [%12];\n\t"
        "ld.shared.volatile.u32 %11, [%12];\n\t"

        "mov.u32 %1, %%clock;\n\t"

        : "=r"(start),
          "=r"(stop),
          "=r"(value0),
          "=r"(value1),
          "=r"(value2),
          "=r"(value3),
          "=r"(value4),
          "=r"(value5),
          "=r"(value6),
          "=r"(value7),
          "=r"(value8),
          "=r"(value9)
        : "r"(shared_address)
        : "memory"
    );

    start_clock[index] = start;
    stop_clock[index] = stop;

    output[index] =
        value0 + value1 + value2 + value3 + value4 +
        value5 + value6 + value7 + value8 + value9;
}
