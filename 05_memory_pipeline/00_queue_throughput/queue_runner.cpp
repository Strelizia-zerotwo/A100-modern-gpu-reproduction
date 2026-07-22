#include <cuda.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <string>
#include <vector>

namespace {

constexpr int kThreads = 32;
constexpr int kSamples = 101;
constexpr std::uint32_t kExpectedLane0 = 10000;

void checkCuda(CUresult result,
               const char* expression,
               const char* file,
               int line)
{
    if (result == CUDA_SUCCESS) {
        return;
    }

    const char* errorName = nullptr;
    const char* errorString = nullptr;

    cuGetErrorName(result, &errorName);
    cuGetErrorString(result, &errorString);

    std::cerr
        << file << ':' << line << ": "
        << (errorName ? errorName : "CUDA_ERROR_UNKNOWN")
        << ": "
        << (errorString ? errorString : "unknown error")
        << '\n'
        << "Failed expression: " << expression << '\n';

    std::exit(EXIT_FAILURE);
}

#define CUDA_CHECK(expression) \
    checkCuda((expression), #expression, __FILE__, __LINE__)

}  // namespace

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::cerr << "Usage: " << argv[0] << " kernel.cubin\n";
        return EXIT_FAILURE;
    }

    CUDA_CHECK(cuInit(0));

    CUdevice device = 0;
    CUDA_CHECK(cuDeviceGet(&device, 0));

    char deviceName[256] = {};
    CUDA_CHECK(cuDeviceGetName(deviceName, sizeof(deviceName), device));

    int major = 0;
    int minor = 0;
    CUDA_CHECK(cuDeviceComputeCapability(&major, &minor, device));

    CUcontext context = nullptr;
    CUDA_CHECK(cuCtxCreate(&context, 0, device));

    CUmodule module = nullptr;
    CUDA_CHECK(cuModuleLoad(&module, argv[1]));

    CUfunction function = nullptr;
    CUDA_CHECK(cuModuleGetFunction(
        &function,
        module,
        "queue_probe"
    ));

    constexpr std::size_t bytes =
        kThreads * sizeof(std::uint32_t);

    CUdeviceptr deviceInput = 0;
    CUdeviceptr deviceStart = 0;
    CUdeviceptr deviceStop = 0;
    CUdeviceptr deviceOutput = 0;

    CUDA_CHECK(cuMemAlloc(&deviceInput, bytes));
    CUDA_CHECK(cuMemAlloc(&deviceStart, bytes));
    CUDA_CHECK(cuMemAlloc(&deviceStop, bytes));
    CUDA_CHECK(cuMemAlloc(&deviceOutput, bytes));

    std::array<std::uint32_t, kThreads> hostInput{};

    for (int index = 0; index < kThreads; ++index) {
        hostInput[index] =
            1000u + static_cast<std::uint32_t>(index);
    }

    CUDA_CHECK(cuMemcpyHtoD(
        deviceInput,
        hostInput.data(),
        bytes
    ));

    std::vector<std::uint32_t> deltas;
    deltas.reserve(kSamples);

    std::map<std::uint32_t, int> resultCounts;

    for (int sample = 0; sample < kSamples; ++sample) {
        void* arguments[] = {
            &deviceInput,
            &deviceStart,
            &deviceStop,
            &deviceOutput,
        };

        CUDA_CHECK(cuLaunchKernel(
            function,
            1, 1, 1,
            kThreads, 1, 1,
            0,
            nullptr,
            arguments,
            nullptr
        ));

        CUDA_CHECK(cuCtxSynchronize());

        std::uint32_t start = 0;
        std::uint32_t stop = 0;
        std::uint32_t result = 0;

        CUDA_CHECK(cuMemcpyDtoH(
            &start,
            deviceStart,
            sizeof(start)
        ));

        CUDA_CHECK(cuMemcpyDtoH(
            &stop,
            deviceStop,
            sizeof(stop)
        ));

        CUDA_CHECK(cuMemcpyDtoH(
            &result,
            deviceOutput,
            sizeof(result)
        ));

        deltas.push_back(stop - start);
        ++resultCounts[result];
    }

    std::sort(deltas.begin(), deltas.end());

    int correctCount = 0;
    int incorrectCount = 0;

    for (const auto& [value, count] : resultCounts) {
        if (value == kExpectedLane0) {
            correctCount += count;
        } else {
            incorrectCount += count;
        }
    }

    std::cout << "GPU: " << deviceName << '\n';
    std::cout << "Compute capability: "
              << major << '.' << minor << '\n';
    std::cout << "Cubin: " << argv[1] << '\n';
    std::cout << "Samples: " << kSamples << '\n';

    std::cout
        << "Clock delta: min=" << deltas.front()
        << " median=" << deltas[deltas.size() / 2]
        << " max=" << deltas.back()
        << " cycles\n";

    std::cout << "Expected lane-0 result: "
              << kExpectedLane0 << '\n';

    std::cout << "Result counts:\n";

    for (const auto& [value, count] : resultCounts) {
        std::cout
            << "  " << std::dec << value
            << " (0x"
            << std::hex << std::setw(8) << std::setfill('0')
            << value
            << std::dec << std::setfill(' ')
            << ") : " << count << '/' << kSamples
            << '\n';
    }

    std::cout
        << "Classification: correct=" << correctCount
        << " incorrect=" << incorrectCount
        << '\n';

    CUDA_CHECK(cuMemFree(deviceOutput));
    CUDA_CHECK(cuMemFree(deviceStop));
    CUDA_CHECK(cuMemFree(deviceStart));
    CUDA_CHECK(cuMemFree(deviceInput));
    CUDA_CHECK(cuModuleUnload(module));
    CUDA_CHECK(cuCtxDestroy(context));

    return EXIT_SUCCESS;
}
