#include <cuda.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <string>
#include <vector>

namespace {

constexpr int kWarpCount = 13;
constexpr int kThreadsPerBlock = kWarpCount * 32;
constexpr int kSamples = 101;

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
        << '\n';

    std::cerr << "Failed expression: " << expression << '\n';
    std::exit(EXIT_FAILURE);
}

#define CUDA_CHECK(expression) \
    checkCuda((expression), #expression, __FILE__, __LINE__)

struct Sample {
    std::array<std::uint32_t, kWarpCount> start{};
    std::array<std::uint32_t, kWarpCount> stop{};
    std::array<std::uint32_t, kWarpCount> hardwareWarp{};
    std::array<std::uint32_t, kWarpCount> sink{};
    std::uint32_t span = std::numeric_limits<std::uint32_t>::max();
};

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
    CUDA_CHECK(cuModuleGetFunction(&function, module, "cggty_probe"));

    const std::size_t bytes =
        static_cast<std::size_t>(kWarpCount) * sizeof(std::uint32_t);

    CUdeviceptr deviceStart = 0;
    CUdeviceptr deviceStop = 0;
    CUdeviceptr deviceHardwareWarp = 0;
    CUdeviceptr deviceSink = 0;

    CUDA_CHECK(cuMemAlloc(&deviceStart, bytes));
    CUDA_CHECK(cuMemAlloc(&deviceStop, bytes));
    CUDA_CHECK(cuMemAlloc(&deviceHardwareWarp, bytes));
    CUDA_CHECK(cuMemAlloc(&deviceSink, bytes));

    std::vector<std::uint32_t> spans;
    spans.reserve(kSamples);

    Sample best;

    for (int sampleIndex = 0; sampleIndex < kSamples; ++sampleIndex) {
        void* arguments[] = {
            &deviceStart,
            &deviceStop,
            &deviceHardwareWarp,
            &deviceSink,
        };

        CUDA_CHECK(cuLaunchKernel(
            function,
            1, 1, 1,
            kThreadsPerBlock, 1, 1,
            0,
            nullptr,
            arguments,
            nullptr
        ));

        CUDA_CHECK(cuCtxSynchronize());

        Sample current;

        CUDA_CHECK(cuMemcpyDtoH(
            current.start.data(),
            deviceStart,
            bytes
        ));

        CUDA_CHECK(cuMemcpyDtoH(
            current.stop.data(),
            deviceStop,
            bytes
        ));

        CUDA_CHECK(cuMemcpyDtoH(
            current.hardwareWarp.data(),
            deviceHardwareWarp,
            bytes
        ));

        CUDA_CHECK(cuMemcpyDtoH(
            current.sink.data(),
            deviceSink,
            bytes
        ));

        const auto minimumStart = *std::min_element(
            current.start.begin(),
            current.start.end()
        );

        const auto maximumStop = *std::max_element(
            current.stop.begin(),
            current.stop.end()
        );

        current.span = maximumStop - minimumStart;
        spans.push_back(current.span);

        if (current.span < best.span) {
            best = current;
        }
    }

    std::sort(spans.begin(), spans.end());

    const auto reference = *std::min_element(
        best.start.begin(),
        best.start.end()
    );

    std::array<int, kWarpCount> order{};
    std::iota(order.begin(), order.end(), 0);

    std::sort(
        order.begin(),
        order.end(),
        [&](int left, int right) {
            const std::uint32_t leftOffset =
                best.start[left] - reference;
            const std::uint32_t rightOffset =
                best.start[right] - reference;

            if (leftOffset != rightOffset) {
                return leftOffset < rightOffset;
            }

            return left < right;
        }
    );

    std::cout << "GPU: " << deviceName << '\n';
    std::cout << "Compute capability: "
              << major << '.' << minor << '\n';
    std::cout << "Cubin: " << argv[1] << '\n';
    std::cout << "Threads: " << kThreadsPerBlock
              << " (" << kWarpCount << " warps)\n";

    std::cout << "Sample span: min=" << spans.front()
              << " median=" << spans[spans.size() / 2]
              << " max=" << spans.back()
              << " cycles\n\n";

    std::cout
        << "logical  hardware  subcore  start+  stop+  delta\n";

    for (int logicalWarp : order) {
        const std::uint32_t hardwareWarp =
            best.hardwareWarp[logicalWarp];

        const std::uint32_t startOffset =
            best.start[logicalWarp] - reference;

        const std::uint32_t stopOffset =
            best.stop[logicalWarp] - reference;

        const std::uint32_t delta =
            best.stop[logicalWarp] - best.start[logicalWarp];

        std::cout
            << std::setw(7) << logicalWarp
            << std::setw(10) << hardwareWarp
            << std::setw(9) << (hardwareWarp % 4)
            << std::setw(8) << startOffset
            << std::setw(7) << stopOffset
            << std::setw(7) << delta
            << '\n';
    }

    CUDA_CHECK(cuMemFree(deviceSink));
    CUDA_CHECK(cuMemFree(deviceHardwareWarp));
    CUDA_CHECK(cuMemFree(deviceStop));
    CUDA_CHECK(cuMemFree(deviceStart));
    CUDA_CHECK(cuModuleUnload(module));
    CUDA_CHECK(cuCtxDestroy(context));

    return EXIT_SUCCESS;
}
