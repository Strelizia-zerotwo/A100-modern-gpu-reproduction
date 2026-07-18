#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#define CUDA_CHECK(call)                                                   \
    do {                                                                   \
        cudaError_t error = (call);                                        \
        if (error != cudaSuccess) {                                        \
            std::fprintf(stderr, "%s:%d: CUDA error: %s\n",                \
                         __FILE__, __LINE__, cudaGetErrorString(error));    \
            std::exit(EXIT_FAILURE);                                       \
        }                                                                  \
    } while (0)

__global__ void toolchain_probe(
    std::uint64_t* timestamps,
    std::uint32_t* result)
{
    std::uint32_t value = threadIdx.x + 1;

    const std::uint64_t start = clock64();

    asm volatile(
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        "add.u32 %0, %0, 1;\n\t"
        : "+r"(value));

    const std::uint64_t stop = clock64();

    if ((threadIdx.x & 31) == 0) {
        timestamps[0] = start;
        timestamps[1] = stop;
        result[0] = value;
    }
}

int main()
{
    int device_count = 0;
    CUDA_CHECK(cudaGetDeviceCount(&device_count));

    std::printf("CUDA-visible device count: %d\n", device_count);

    if (device_count != 1) {
        std::fprintf(
            stderr,
            "Expected exactly one CUDA-visible GPU, but found %d\n",
            device_count);
        return EXIT_FAILURE;
    }

    CUDA_CHECK(cudaSetDevice(0));

    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));

    std::printf("Logical device: 0\n");
    std::printf("GPU name: %s\n", properties.name);
    std::printf(
        "Compute capability: %d.%d\n",
        properties.major,
        properties.minor);
    std::printf("SM count: %d\n", properties.multiProcessorCount);
    std::printf("Warp size: %d\n", properties.warpSize);

    std::uint64_t* timestamps = nullptr;
    std::uint32_t* result = nullptr;

    CUDA_CHECK(cudaMallocManaged(&timestamps, 2 * sizeof(*timestamps)));
    CUDA_CHECK(cudaMallocManaged(&result, sizeof(*result)));

    timestamps[0] = 0;
    timestamps[1] = 0;
    result[0] = 0;

    toolchain_probe<<<1, 32>>>(timestamps, result);

    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    const std::uint64_t elapsed = timestamps[1] - timestamps[0];

    std::printf("Start clock: %llu\n",
                static_cast<unsigned long long>(timestamps[0]));
    std::printf("Stop clock:  %llu\n",
                static_cast<unsigned long long>(timestamps[1]));
    std::printf("Clock delta: %llu cycles\n",
                static_cast<unsigned long long>(elapsed));
    std::printf("Result: %u, expected: 9\n", result[0]);

    const bool passed =
        properties.major == 8 &&
        properties.minor == 0 &&
        result[0] == 9 &&
        timestamps[1] > timestamps[0];

    CUDA_CHECK(cudaFree(result));
    CUDA_CHECK(cudaFree(timestamps));

    if (!passed) {
        std::fprintf(stderr, "Toolchain probe failed\n");
        return EXIT_FAILURE;
    }

    std::printf("Toolchain probe passed\n");
    return EXIT_SUCCESS;
}
