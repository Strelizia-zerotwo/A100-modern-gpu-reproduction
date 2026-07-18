#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

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

#define FADD_1 \
    "add.rn.f32 %2, %2, %3;\n\t"

#define FADD_2 \
    FADD_1 FADD_1

#define FADD_4 \
    FADD_2 FADD_2

#define FADD_8 \
    FADD_4 FADD_4

#define FADD_16 \
    FADD_8 FADD_8

#define FADD_32 \
    FADD_16 FADD_16

#define FADD_64 \
    FADD_32 FADD_32

#define FADD_128 \
    FADD_64 FADD_64

#define DEFINE_FADD_KERNEL(kernel_name, fadd_body)                          \
    extern "C" __global__ void kernel_name(                                \
        std::uint64_t* deltas,                                              \
        float* results,                                                     \
        int sample_index,                                                   \
        float seed,                                                         \
        float addend)                                                       \
    {                                                                       \
        std::uint64_t start_clock = 0;                                      \
        std::uint64_t stop_clock = 0;                                       \
        float value = seed;                                                 \
                                                                            \
        asm volatile(                                                       \
            "mov.u64 %0, %%clock64;\n\t"                                    \
            fadd_body                                                       \
            "mov.u64 %1, %%clock64;\n\t"                                    \
            : "=l"(start_clock),                                            \
              "=l"(stop_clock),                                             \
              "+f"(value)                                                   \
            : "f"(addend)                                                   \
            : "memory");                                                    \
                                                                            \
        if (threadIdx.x == 0) {                                             \
            deltas[sample_index] = stop_clock - start_clock;                \
            results[sample_index] = value;                                  \
        }                                                                   \
    }

DEFINE_FADD_KERNEL(fadd_chain_64, FADD_64)
DEFINE_FADD_KERNEL(fadd_chain_128, FADD_128)

struct Statistics {
    std::uint64_t minimum;
    std::uint64_t median;
    std::uint64_t maximum;
};

Statistics summarize(
    const std::uint64_t* values,
    int count)
{
    std::vector<std::uint64_t> sorted(values, values + count);
    std::sort(sorted.begin(), sorted.end());

    return {
        sorted.front(),
        sorted[static_cast<std::size_t>(count / 2)],
        sorted.back()
    };
}

int main()
{
    constexpr int warmup_iterations = 20;
    constexpr int samples = 101;
    constexpr float seed = 1.0f;
    constexpr float addend = 1.0f;

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
    std::printf("Samples: %d\n", samples);

    if (properties.major != 8 || properties.minor != 0) {
        std::fprintf(stderr, "Expected an sm_80 GPU\n");
        return EXIT_FAILURE;
    }

    std::uint64_t* deltas_64 = nullptr;
    std::uint64_t* deltas_128 = nullptr;
    float* results_64 = nullptr;
    float* results_128 = nullptr;

    CUDA_CHECK(cudaMallocManaged(
        &deltas_64,
        samples * sizeof(*deltas_64)));
    CUDA_CHECK(cudaMallocManaged(
        &deltas_128,
        samples * sizeof(*deltas_128)));
    CUDA_CHECK(cudaMallocManaged(
        &results_64,
        samples * sizeof(*results_64)));
    CUDA_CHECK(cudaMallocManaged(
        &results_128,
        samples * sizeof(*results_128)));

    for (int iteration = 0;
         iteration < warmup_iterations;
         ++iteration) {
        fadd_chain_64<<<1, 32>>>(
            deltas_64,
            results_64,
            0,
            seed,
            addend);

        fadd_chain_128<<<1, 32>>>(
            deltas_128,
            results_128,
            0,
            seed,
            addend);
    }

    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    for (int sample = 0; sample < samples; ++sample) {
        fadd_chain_64<<<1, 32>>>(
            deltas_64,
            results_64,
            sample,
            seed,
            addend);

        fadd_chain_128<<<1, 32>>>(
            deltas_128,
            results_128,
            sample,
            seed,
            addend);
    }

    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    bool results_correct = true;

    for (int sample = 0; sample < samples; ++sample) {
        if (results_64[sample] != 65.0f) {
            std::fprintf(
                stderr,
                "Unexpected 64-FADD result at sample %d: %.9g\n",
                sample,
                results_64[sample]);
            results_correct = false;
        }

        if (results_128[sample] != 129.0f) {
            std::fprintf(
                stderr,
                "Unexpected 128-FADD result at sample %d: %.9g\n",
                sample,
                results_128[sample]);
            results_correct = false;
        }
    }

    const Statistics statistics_64 =
        summarize(deltas_64, samples);
    const Statistics statistics_128 =
        summarize(deltas_128, samples);

    const double differential_spacing =
        static_cast<double>(
            statistics_128.median -
            statistics_64.median) /
        64.0;

    std::printf(
        "64 dependent FADDs:  min=%llu median=%llu max=%llu cycles\n",
        static_cast<unsigned long long>(statistics_64.minimum),
        static_cast<unsigned long long>(statistics_64.median),
        static_cast<unsigned long long>(statistics_64.maximum));

    std::printf(
        "128 dependent FADDs: min=%llu median=%llu max=%llu cycles\n",
        static_cast<unsigned long long>(statistics_128.minimum),
        static_cast<unsigned long long>(statistics_128.median),
        static_cast<unsigned long long>(statistics_128.maximum));

    std::printf(
        "Differential dependent-FADD spacing: %.4f cycles/instruction\n",
        differential_spacing);

    std::printf(
        "Result check: %s\n",
        results_correct ? "PASS" : "FAIL");

    CUDA_CHECK(cudaFree(results_128));
    CUDA_CHECK(cudaFree(results_64));
    CUDA_CHECK(cudaFree(deltas_128));
    CUDA_CHECK(cudaFree(deltas_64));

    return results_correct ? EXIT_SUCCESS : EXIT_FAILURE;
}
