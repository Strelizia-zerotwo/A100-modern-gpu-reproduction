#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#define CUDA_CHECK(call)                                                   \
    do {                                                                   \
        cudaError_t error = (call);                                        \
        if (error != cudaSuccess) {                                        \
            std::fprintf(                                                  \
                stderr,                                                    \
                "%s:%d: CUDA error: %s\n",                                 \
                __FILE__,                                                  \
                __LINE__,                                                  \
                cudaGetErrorString(error));                                \
            std::exit(EXIT_FAILURE);                                       \
        }                                                                  \
    } while (0)

extern "C" __global__ void stall_counter_probe(
    std::uint32_t* start_clocks,
    std::uint32_t* stop_clocks,
    float* results)
{
    std::uint32_t start_clock;
    std::uint32_t stop_clock;

    float value_1;
    float value_2;
    float value_3;
    float result;

    asm volatile(
        "mov.f32 %0, 0f3f800000;\n\t"
        "mov.f32 %1, 0f3f800000;\n\t"
        "mov.f32 %2, 0f3f800000;\n\t"
        "mov.u32 %4, %%clock;\n\t"
        "add.rn.f32 %0, %1, %2;\n\t"
        "fma.rn.f32 %3, %0, %0, %0;\n\t"
        "mov.u32 %5, %%clock;\n\t"
        : "=&f"(value_1),
          "=&f"(value_2),
          "=&f"(value_3),
          "=&f"(result),
          "=&r"(start_clock),
          "=&r"(stop_clock)
        :
        : "memory");

    if (threadIdx.x == 0) {
        start_clocks[0] = start_clock;
        stop_clocks[0] = stop_clock;
        results[0] = result;
    }
}

int main()
{
    int device_count = 0;
    CUDA_CHECK(cudaGetDeviceCount(&device_count));

    if (device_count != 1) {
        std::fprintf(
            stderr,
            "Expected exactly one CUDA-visible GPU, found %d\n",
            device_count);
        return EXIT_FAILURE;
    }

    CUDA_CHECK(cudaSetDevice(0));

    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));

    std::printf("GPU: %s\n", properties.name);
    std::printf(
        "Compute capability: %d.%d\n",
        properties.major,
        properties.minor);

    std::uint32_t* start_clock = nullptr;
    std::uint32_t* stop_clock = nullptr;
    float* result = nullptr;

    CUDA_CHECK(cudaMallocManaged(
        &start_clock,
        sizeof(*start_clock)));
    CUDA_CHECK(cudaMallocManaged(
        &stop_clock,
        sizeof(*stop_clock)));
    CUDA_CHECK(cudaMallocManaged(
        &result,
        sizeof(*result)));

    *start_clock = 0;
    *stop_clock = 0;
    *result = 0.0f;

    stall_counter_probe<<<1, 32>>>(
        start_clock,
        stop_clock,
        result);

    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    const std::uint32_t elapsed =
        *stop_clock - *start_clock;

    std::printf("Start clock: %u\n", *start_clock);
    std::printf("Stop clock:  %u\n", *stop_clock);
    std::printf("Clock delta: %u cycles\n", elapsed);
    std::printf("Result: %.9g\n", *result);
    std::printf("Expected correct result: 6\n");
    std::printf("Expected stale-value result: 2\n");

    CUDA_CHECK(cudaFree(result));
    CUDA_CHECK(cudaFree(stop_clock));
    CUDA_CHECK(cudaFree(start_clock));

    return EXIT_SUCCESS;
}
