#include <cuda_runtime.h>
#include <stdint.h>

extern "C" __global__
void dep_counter_probe(const uint32_t* input,
                       uint32_t* output)
{
    const uint32_t index = threadIdx.x;

    const volatile uint32_t* volatile_input =
        reinterpret_cast<const volatile uint32_t*>(input);

    const uint32_t value = volatile_input[index];

    output[index] = value + 1u;
}
