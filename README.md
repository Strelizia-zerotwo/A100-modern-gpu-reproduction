<div align="center">

# NVIDIA A100 GPU Core Reverse Engineering

**在 GA100 上复现《Dissecting and Modeling the Architecture of Modern GPU Cores》的硬件逆向实验**

[![GPU](https://img.shields.io/badge/GPU-NVIDIA%20A100-76B900?logo=nvidia&logoColor=white)](https://www.nvidia.com/en-us/data-center/a100/)
[![Architecture](https://img.shields.io/badge/Architecture-Ampere%20GA100-1f6feb)](#实验平台)
[![CUDA](https://img.shields.io/badge/CUDA-12.4-5c5c5c?logo=nvidia&logoColor=white)](#环境准备)
[![Progress](https://img.shields.io/badge/Progress-2%20experiments%20verified-2ea44f)](#复现进度)

通过可控微基准、SASS 控制位修改和真实硬件周期测量，逐步重建现代 NVIDIA GPU Core 的执行与调度机制。

</div>

---

## 项目简介

NVIDIA 没有公开现代 GPU Core 的完整微架构。本项目不依赖性能计数器猜测，而是直接构造小型 SASS 指令序列，在真实 A100 上改变单一变量并测量周期与计算结果。

当前阶段聚焦硬件逆向，暂不进行 Accel-Sim 集成和最终仿真误差分析。主要研究对象包括：

- SASS control bits 与固定延迟数据依赖；
- Register File bank、读端口和冲突行为；
- Register File Cache 与 operand reuse；
- Warp issue scheduler、Yield、barrier 和 wait mask；
- Memory pipeline 与 instruction front-end。

> 当前已完成论文 Listing 2 的 Stall Counter 实验，以及 Listing 1 的 Register File Read Conflict 实验。两个实验均在 A100 上得到稳定、可重复的硬件证据。

## 实验平台

| 项目 | 配置 |
|---|---|
| GPU | NVIDIA A100-SXM4-40GB |
| 微架构 | Ampere GA100 |
| Compute Capability | 8.0 (`sm_80`) |
| SM 数量 | 108 |
| Driver | 550.54.14 |
| CUDA Toolkit | 12.4 |
| 实验 GPU | 物理 GPU 6 |
| GPU 隔离 | `CUDA_VISIBLE_DEVICES=6` |
| SASS 工具 | CUAssembler、cuobjdump、nvdisasm |
| Cubin 执行 | CUDA Driver API |
| 每种配置 | 20 次预热 + 101 次采样 |

## 逆向工作流

```mermaid
flowchart LR
    A[CUDA scaffold] -->|nvcc / ptxas| B[合法 sm_80 cubin]
    B -->|CUAssembler dsass| C[带控制字段的 cuasm]
    C -->|单变量修改| D[实验变体]
    D -->|CUAssembler| E[修改后的 cubin]
    E -->|CUDA Driver API| F[A100 硬件执行]
    F --> G[周期与结果验证]
    G -->|反驳或支持| H[微架构假设]
```

实验遵循四条规则：

1. **单变量**：同组 cubin 只改变一个控制位或寄存器编号。
2. **不重新编译 SASS**：Driver API 直接加载修改后的 cubin，避免 ptxas 修复或重排。
3. **双重验证**：同时检查 `SR_CLOCKLO` 周期和最终数据值。
4. **先做对照**：通过 NOP、独立指令和不同执行通路拆分重叠的硬件限制。

## 已验证结论

### 1. Stall Counter 与固定延迟 RAW 依赖

对应论文第 4 节和 **Listing 2**。

核心指令窗口：

```sass
CS2R.32 R11, SR_CLOCKLO
NOP
FADD R8, R9, R10        // Producer，仅修改这里的 Stall Counter
FFMA R12, R8, R8, R8    // Consumer，立即读取 R8
NOP
CS2R.32 R13, SR_CLOCKLO
```

受控输入满足：

```text
FADD 正确结果：R8  = 1 + 1     = 2
FFMA 正确结果：R12 = 2 * 2 + 2 = 6
FFMA 读取旧值：R12 = 1 * 1 + 1 = 2
```

| Stall | Clock delta | FFMA 结果 | 101 次采样 | 判断 |
|---:|---:|---:|---:|---|
| S01 | 6 | 2 | 101/101 | 读取旧值 |
| S02 | 6 | 2 | 101/101 | 读取旧值 |
| S03 | 7 | 2 | 101/101 | 读取旧值 |
| **S04** | **8** | **6** | **101/101** | **首次正确** |
| S05 | 9 | 6 | 101/101 | 正确 |
| S06 | 10 | 6 | 101/101 | 正确 |
| S07 | 11 | 6 | 101/101 | 正确 |
| S08 | 12 | 6 | 101/101 | 正确 |

**结论：** 该固定延迟 `FADD -> FFMA` RAW 依赖的最小正确值为 S04。S01-S03 时 consumer 会真实执行并读取旧值，说明硬件不会用传统动态 scoreboard 完整兜底，而是依赖编译器编码在 producer SASS 中的 stall counter。

A100 的周期满足：

```text
clock_delta = max(6, stall_value + 4)
```

论文报告 S01=5、S04=8，而 A100 实测 S01=6、S04=8。我们进一步完成了控制实验：

| 指令窗口 | 周期 |
|---|---:|
| `NOP -> NOP` | 5 |
| `FADD -> NOP` | 5 |
| `NOP -> FFMA` | 5 |
| `FADD -> independent FFMA` | 6 |
| `FADD -> dependent FFMA` | 6 |
| `FADD -> FADD` | 6 |
| `FADD -> IADD3` | 5 |
| `FADD -> MOV` | 5 |

因此，多出的周期不是计时开销或 RAW 保护，而是 A100 上测试到的连续 FP32 warp 指令结构限制。

### 2. Register File Read Conflicts

对应论文第 3 节方法示例、**Listing 1** 和第 5.3 节。

实验关闭 operand reuse，固定第一条指令使用三个偶数源寄存器，只改变下一条 FFMA 后两个源寄存器的奇偶组合：

```sass
// OO：even / odd / odd
FFMA R12, R10, R5, R7

// EO：even / even / odd
FFMA R12, R10, R6, R7

// EE：even / even / even
FFMA R12, R10, R6, R8
```

| 指令序列 | OO | EO | EE |
|---|---:|---:|---:|
| `FFMA -> FFMA` | 6 | 6 | 7 |
| `IADD3 -> FFMA` | **5** | **6** | **7** |

`IADD3 -> FFMA` 对照消除了连续 FP32 指令固有的结构气泡，直接暴露出 0、1、2 个 RF read-conflict bubbles，与论文结果一致。

**结论：** A100 普通寄存器表现出两个 bank，映射与寄存器编号奇偶一致：

```text
bank_id = register_id mod 2
偶数寄存器 -> Bank 0
奇数寄存器 -> Bank 1
```

原始 `FFMA -> FFMA` 中，两种限制发生重叠：

```text
实际气泡 = max(FP32 结构气泡, Register File 气泡)
```

| 组合 | FP32 气泡 | RF 气泡 | 实际气泡 | 总周期 |
|---|---:|---:|---:|---:|
| OO | 1 | 0 | 1 | 6 |
| EO | 1 | 1 | 1 | 6 |
| EE | 1 | 2 | 2 | 7 |

## 复现进度

| 模块 | 论文位置 | 状态 | A100 结果 |
|---|---|---|---|
| 工具链与 Cubin 往返 | Section 3 | 已完成 | CUAssembler round-trip 通过 |
| Stall Counter | Section 4 / Listing 2 | 已完成 | 临界值 S04 |
| FP32 结构限制 | A100 差异分析 | 已完成 | 连续 FP32 有 1-cycle 气泡 |
| RF Read Conflict | Section 5.3 / Listing 1 | 已完成 | OO/EO/EE = 5/6/7 |
| Register File Cache | Section 5.3.1 / Listing 4 | 下一项 | 待测试 reuse bit |
| Yield Bit | Section 4 | 待开始 | - |
| Read/Write Barrier | Section 4 | 待开始 | - |
| Warp Scheduler | Section 5.1 | 待开始 | - |
| Memory Pipeline | Section 5.4 | 待开始 | - |
| Instruction Front-end | Section 5.2 | 待开始 | - |

## 仓库结构

```text
modern-gpu-reproduction/
|-- 00_toolchain/                         # CUDA 与 CUAssembler 验证
|-- 01_control_bits/
|   |-- 00_fadd_latency/                  # 初始时序探针
|   `-- 01_stall_counter/                 # Listing 2 与控制实验
|-- 02_register_file/
|   `-- 00_read_conflicts/                # Listing 1 与 IADD3 对照
|-- third_party/
|   `-- CuAssembler/                      # 本地依赖，不提交到主仓库
|-- EXPERIMENT_LOG.md                     # 完整实验记录
|-- env.sh                                # 项目环境变量
`-- README.md
```

## 环境准备

### 1. 激活项目环境

```bash
cd /root/wym/modern-gpu-reproduction
conda activate cuasm
source env.sh

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=6
```

确认当前进程只看到一张 CUDA GPU：

```bash
python - <<'PY'
import os
print("CONDA_DEFAULT_ENV =", os.getenv("CONDA_DEFAULT_ENV"))
print("CUDA_VISIBLE_DEVICES =", os.getenv("CUDA_VISIBLE_DEVICES"))
PY
```

### 2. 安装 CUAssembler

```bash
mkdir -p third_party
cd third_party
git clone https://github.com/cloudcores/CuAssembler.git

conda create -n cuasm python=3.10 -y
conda activate cuasm
pip install sympy pyelftools

export CUAS_HOME="$PWD/CuAssembler"
export PYTHONPATH="$CUAS_HOME:${PYTHONPATH:-}"
```

### 3. 常用命令

```bash
# Cubin -> CUASM，显示控制字段
python "$CUAS_HOME/bin/dsass.py" input.cubin -o output.cuasm

# CUASM -> Cubin
python "$CUAS_HOME/bin/cuasm.py" input.cuasm -o output.cubin -v

# 检查最终 SASS 与资源用量
nvdisasm --print-code output.cubin
cuobjdump --dump-sass output.cubin
cuobjdump --dump-resource-usage output.cubin
```

## 结果解释边界

- 当前结论针对 NVIDIA A100 GA100，不默认推广到所有 Ampere、Turing 或 Blackwell GPU。
- CUDA 12.4 足以进行本项目的硬件 SASS 逆向；涉及编译器行为比较时，CUDA 版本仍是实验变量。
- `CUDA_VISIBLE_DEVICES=6` 只影响当前 shell 及其子进程，不会改变其他用户看到的 GPU。
- 非法控制位或不匹配的 cubin 元数据可能触发 `CUDA_ERROR_ILLEGAL_INSTRUCTION`，因此每个变体都必须先反汇编验证。
- 本项目中的 `stale/correct` 分类只适用于对应受控数据实验，不能机械套用到所有时序测试。

## 文档

- [完整复现实验记录](EXPERIMENT_LOG.md)
- [原论文 PDF](https://doi.org/10.1145/3725843.3756064)
- [CUAssembler](https://github.com/cloudcores/CuAssembler)
- [CUDA Binary Utilities](https://docs.nvidia.com/cuda/cuda-binary-utilities/)
- [NVIDIA A100 Tensor Core GPU Architecture](https://www.nvidia.com/en-us/data-center/ampere-architecture/)

## 研究范围

本仓库用于学术研究与可重复微架构实验。当前结果不包含生产环境稳定性保证，也不代表 NVIDIA 官方文档或官方架构声明。

---

<div align="center">

**当前阶段：硬件逆向实验进行中**  
最后更新：2026-07-20  
维护者：[@Strelizia-zerotwo](https://github.com/Strelizia-zerotwo)

</div>

### RFC / reuse bit 实验结果

对应论文第 5.3.1 节和 Listing 4。A100 上已经验证：

| 实验 | Clock delta | 结论 |
|---|---:|---|
| `NO_REUSE` | 7 | 普通 Register File 读取 |
| `SAME_SLOT_HIT` | 6 | 相同寄存器、相同 operand slot，RFC 命中 |
| `DIFFERENT_SLOT` | 7 | 相同寄存器但 operand slot 不同，RFC miss |
| `CONSUME` | 9 | 命中但未再次设置 `.reuse`，entry 被消费 |
| `RETAIN` | 8 | 命中并再次设置 `.reuse`，entry 被保留 |
| `OTHER_BANK_2INST` | 6 | 不同 bank，不驱逐原 entry |
| `SAME_BANK_2INST` | 7 | 同 bank、同 slot，第二条指令自身多一个冲突周期 |
| `OTHER_BANK` | 8 | 第三条 probe 命中原 RFC entry |
| `SAME_BANK` | 10 | 原 entry 被驱逐，第三条 probe miss |

每种配置均执行 101 次，`min=median=max`。

两指令基线差异：

```text
SAME_BANK_2INST - OTHER_BANK_2INST = 7 - 6 = 1 cycle
加入第三条 probe 后的总差异：
SAME_BANK - OTHER_BANK = 10 - 8 = 2 cycles
因此 RFC 驱逐本身带来的额外差异为：
2 - 1 = 1 cycle
结论：A100 的 RFC 命中条件同时依赖 register ID、register bank 和 source operand slot。命中后不设置 .reuse 会消费 entry，再次设置 .reuse 会保留 entry；同 bank、同 slot 的其他寄存器访问会驱逐原 entry，不同 bank 的访问不会驱逐原 entry。
