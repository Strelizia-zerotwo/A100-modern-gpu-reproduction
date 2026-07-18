# A100 GPU Microarchitecture Reverse Engineering

复现论文 *"Dissecting and Modeling the Architecture of Modern GPU Cores"* 在 NVIDIA A100 (GA100) 上的硬件逆向工程实验。

## 🎯 项目目标

通过微基准测试（microbenchmarking）和 SASS 级别的代码注入，逆向工程 NVIDIA A100 GPU 的微架构细节，包括：

- 控制位机制（Stall Counter, Yield, Barriers）
- 寄存器堆（Register File）结构和 bank conflict
- Warp 调度器行为
- 内存流水线特性
- 指令延迟和吞吐量

## 🖥️ 硬件环境

| 组件 | 规格 |
|------|------|
| **GPU** | NVIDIA A100-SXM4-40GB |
| **Compute Capability** | 8.0 (sm_80, Ampere GA100) |
| **SM Count** | 108 |
| **Driver** | 550.54.14 |
| **CUDA** | 12.4 |

## 📁 项目结构

modern-gpu-reproduction/
├── 00_toolchain/              # 工具链验证
│   ├── probe.cu               # 基础功能测试
│   ├── probe_sm80.cubin       # 编译产物
│   └── roundtrip/             # CUAssembler 往返测试
├── 01_control_bits/           # 控制位逆向实验
│   ├── 00_fadd_latency/       # FADD 延迟基准测试
│   └── 01_stall_counter/      # ✓ Stall counter 实验
│       ├── stall_counter.cu   # CUDA 源代码
│       ├── stall_runner.cpp   # Driver API 运行器
│       ├── make_variants.py   # 生成不同 stall 的 cubin
│       ├── variants/          # S01-S08 cubin 变体
│       └── results/           # 实验结果
├── third_party/
│   └── CuAssembler/           # SASS 汇编器（需手动安装）
├── env.sh                     # 环境变量配置
├── .gitignore
└── README.md

## ✅ 已完成实验

### Listing 2: Stall Counter Experiment

**实验目标**：验证 A100 使用编译器嵌入的 stall counter 控制位来管理寄存器 RAW 依赖，而非动态记分板机制。

#### 实验设计

```c
// 核心代码序列
CS2R R11, SR_CLOCKLO;           // ← 开始计时
FADD R8, R9, R10;               // ← Producer（设置 stall S01-S08）
FFMA R12, R8, R8, R8;           // ← Consumer（依赖 R8）
CS2R R13, SR_CLOCKLO;           // ← 结束计时
关键发现
Stall Counter	Clock Cycles	Result Value	状态	说明
S01-S03	6	2.0 (stale)	❌	读取旧值
S04-S08	8	6.0 (correct)	✅	读取新值

临界 Stall: S04 (4 个时钟周期)
结论
A100 不使用动态记分板管理算术运算的 RAW 依赖
Stall < 4: Consumer 过早读取 R8，获得初始化值 2.0f
Stall ≥ 4: FADD 完成写入，Consumer 读取正确计算结果 6.0f
🛠️ 核心工具链
1. CUAssembler
手工汇编/反汇编 SASS 代码，支持查看和修改控制位。
2. Driver API Runner
动态加载任意 cubin 文件，绕过 nvcc 的优化和重编译。
🚀 快速开始
详见仓库内完整文档。
Status: 🔬 Active Development
Last Updated: 2026-07-19
