#include <cuda.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <vector>

#define CU_CHECK(call)                                                       \
    do {                                                                     \
        CUresult status = (call);                                            \
        if (status != CUDA_SUCCESS) {                                        \
            const char* name = nullptr;                                      \
            const char* message = nullptr;                                   \
            cuGetErrorName(status, &name);                                   \
            cuGetErrorString(status, &message);                              \
            std::fprintf(                                                    \
                stderr,                                                      \
                "%s:%d: %s: %s\n",                                           \
                __FILE__,                                                    \
                __LINE__,                                                    \
                name ? name : "CUDA_ERROR",                                  \
                message ? message : "unknown error");                        \
            std::exit(EXIT_FAILURE);                                         \
        }                                                                    \
    } while (0)

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s <stall.cubin>\n", argv[0]);
        return EXIT_FAILURE;
    }

    constexpr int warmup_iterations = 20;
    constexpr int samples = 101;

    CU_CHECK(cuInit(0));

    int device_count = 0;
    CU_CHECK(cuDeviceGetCount(&device_count));

    if (device_count != 1) {
        std::fprintf(
            stderr,
            "Expected exactly one CUDA-visible GPU, found %d\n",
            device_count);
        return EXIT_FAILURE;
    }

    CUdevice device;
    CU_CHECK(cuDeviceGet(&device, 0));

    char device_name[256] = {};
    CU_CHECK(cuDeviceGetName(
        device_name,
        sizeof(device_name),
        device));

    int major = 0;
    int minor = 0;

    CU_CHECK(cuDeviceGetAttribute(
        &major,
        CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR,
        device));

    CU_CHECK(cuDeviceGetAttribute(
        &minor,
        CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR,
        device));

    std::printf("GPU: %s\n", device_name);
    std::printf("Compute capability: %d.%d\n", major, minor);
    std::printf("Cubin: %s\n", argv[1]);

    CUcontext context;
    CU_CHECK(cuCtxCreate(&context, 0, device));

    CUmodule module;
    CU_CHECK(cuModuleLoad(&module, argv[1]));

    CUfunction function;
    CU_CHECK(cuModuleGetFunction(
        &function,
        module,
        "stall_counter_probe"));

    CUdeviceptr device_start;
    CUdeviceptr device_stop;
    CUdeviceptr device_result;

    CU_CHECK(cuMemAlloc(
        &device_start,
        sizeof(std::uint32_t)));

    CU_CHECK(cuMemAlloc(
        &device_stop,
        sizeof(std::uint32_t)));

    CU_CHECK(cuMemAlloc(
        &device_result,
        sizeof(float)));

    void* arguments[] = {
        &device_start,
        &device_stop,
        &device_result
    };

    for (int iteration = 0;
         iteration < warmup_iterations;
         ++iteration) {
        CU_CHECK(cuLaunchKernel(
            function,
            1, 1, 1,
            32, 1, 1,
            0,
            nullptr,
            arguments,
            nullptr));
    }

    CU_CHECK(cuCtxSynchronize());

    std::vector<std::uint32_t> deltas;
    deltas.reserve(samples);

    std::map<float, int> result_counts;

    for (int sample = 0; sample < samples; ++sample) {
        CU_CHECK(cuLaunchKernel(
            function,
            1, 1, 1,
            32, 1, 1,
            0,
            nullptr,
            arguments,
            nullptr));

        CU_CHECK(cuCtxSynchronize());

        std::uint32_t start = 0;
        std::uint32_t stop = 0;
        float result = 0.0f;

        CU_CHECK(cuMemcpyDtoH(
            &start,
            device_start,
            sizeof(start)));

        CU_CHECK(cuMemcpyDtoH(
            &stop,
            device_stop,
            sizeof(stop)));

        CU_CHECK(cuMemcpyDtoH(
            &result,
            device_result,
            sizeof(result)));

        deltas.push_back(stop - start);
        result_counts[result] += 1;
    }

    std::sort(deltas.begin(), deltas.end());

    const std::uint32_t minimum = deltas.front();
    const std::uint32_t median =
        deltas[static_cast<std::size_t>(samples / 2)];
    const std::uint32_t maximum = deltas.back();

    std::printf(
        "Clock delta: min=%u median=%u max=%u cycles\n",
        minimum,
        median,
        maximum);

    std::printf("Result counts:\n");

    for (const auto& entry : result_counts) {
        std::printf(
            "  %.9g : %d/%d\n",
            entry.first,
            entry.second,
            samples);
    }

    const int stale_count =
        result_counts.count(2.0f)
            ? result_counts[2.0f]
            : 0;

    const int correct_count =
        result_counts.count(6.0f)
            ? result_counts[6.0f]
            : 0;

    std::printf(
        "Classification: stale=%d correct=%d other=%d\n",
        stale_count,
        correct_count,
        samples - stale_count - correct_count);

    CU_CHECK(cuMemFree(device_result));
    CU_CHECK(cuMemFree(device_stop));
    CU_CHECK(cuMemFree(device_start));
    CU_CHECK(cuModuleUnload(module));
    CU_CHECK(cuCtxDestroy(context));

    return EXIT_SUCCESS;
}
