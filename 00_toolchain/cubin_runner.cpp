#include <cuda.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#define CU_CHECK(call)                                                       \
    do {                                                                     \
        CUresult status = (call);                                            \
        if (status != CUDA_SUCCESS) {                                        \
            const char* error_name = nullptr;                                \
            const char* error_string = nullptr;                              \
            cuGetErrorName(status, &error_name);                             \
            cuGetErrorString(status, &error_string);                         \
            std::fprintf(                                                    \
                stderr,                                                      \
                "%s:%d: CUDA Driver error %s: %s\n",                         \
                __FILE__,                                                    \
                __LINE__,                                                    \
                error_name ? error_name : "UNKNOWN",                         \
                error_string ? error_string : "UNKNOWN");                    \
            std::exit(EXIT_FAILURE);                                         \
        }                                                                    \
    } while (0)

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s <file.cubin>\n", argv[0]);
        return EXIT_FAILURE;
    }

    const char* cubin_path = argv[1];
    constexpr const char* kernel_name = "_Z15toolchain_probePmPj";

    CU_CHECK(cuInit(0));

    int device_count = 0;
    CU_CHECK(cuDeviceGetCount(&device_count));

    if (device_count != 1) {
        std::fprintf(
            stderr,
            "Expected exactly one CUDA-visible device, found %d\n",
            device_count);
        return EXIT_FAILURE;
    }

    CUdevice device;
    CU_CHECK(cuDeviceGet(&device, 0));

    char device_name[256] = {};
    CU_CHECK(cuDeviceGetName(device_name, sizeof(device_name), device));

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

    std::printf("CUDA-visible device count: %d\n", device_count);
    std::printf("Logical device: 0\n");
    std::printf("GPU name: %s\n", device_name);
    std::printf("Compute capability: %d.%d\n", major, minor);
    std::printf("Cubin: %s\n", cubin_path);

    CUcontext context;
    CU_CHECK(cuCtxCreate(&context, 0, device));

    CUmodule module;
    CU_CHECK(cuModuleLoad(&module, cubin_path));

    CUfunction kernel;
    CU_CHECK(cuModuleGetFunction(&kernel, module, kernel_name));

    CUdeviceptr device_timestamps;
    CUdeviceptr device_result;

    CU_CHECK(cuMemAlloc(
        &device_timestamps,
        2 * sizeof(std::uint64_t)));
    CU_CHECK(cuMemAlloc(
        &device_result,
        sizeof(std::uint32_t)));

    CU_CHECK(cuMemsetD8(
        device_timestamps,
        0,
        2 * sizeof(std::uint64_t)));
    CU_CHECK(cuMemsetD8(
        device_result,
        0,
        sizeof(std::uint32_t)));

    void* kernel_arguments[] = {
        &device_timestamps,
        &device_result
    };

    CU_CHECK(cuLaunchKernel(
        kernel,
        1, 1, 1,
        32, 1, 1,
        0,
        nullptr,
        kernel_arguments,
        nullptr));

    CU_CHECK(cuCtxSynchronize());

    std::uint64_t timestamps[2] = {};
    std::uint32_t result = 0;

    CU_CHECK(cuMemcpyDtoH(
        timestamps,
        device_timestamps,
        sizeof(timestamps)));
    CU_CHECK(cuMemcpyDtoH(
        &result,
        device_result,
        sizeof(result)));

    const std::uint64_t delta = timestamps[1] - timestamps[0];

    std::printf(
        "Start clock: %llu\n",
        static_cast<unsigned long long>(timestamps[0]));
    std::printf(
        "Stop clock:  %llu\n",
        static_cast<unsigned long long>(timestamps[1]));
    std::printf(
        "Clock delta: %llu cycles\n",
        static_cast<unsigned long long>(delta));
    std::printf("Result: %u, expected: 9\n", result);

    const bool passed =
        major == 8 &&
        minor == 0 &&
        timestamps[1] > timestamps[0] &&
        result == 9;

    CU_CHECK(cuMemFree(device_result));
    CU_CHECK(cuMemFree(device_timestamps));
    CU_CHECK(cuModuleUnload(module));
    CU_CHECK(cuCtxDestroy(context));

    if (!passed) {
        std::fprintf(stderr, "Cubin execution failed validation\n");
        return EXIT_FAILURE;
    }

    std::printf("Cubin execution passed\n");
    return EXIT_SUCCESS;
}
