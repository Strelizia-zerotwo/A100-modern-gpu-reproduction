<div align="center">

# NVIDIA A100 GPU Core Reverse Engineering

**在 GA100 上复现《Dissecting and Modeling the Architecture of Modern GPU Cores》的硬件逆向实验**

[![GPU](https://img.shields.io/badge/GPU-NVIDIA%20A100-76B900?logo=nvidia&logoColor=white)](https://www.nvidia.com/en-us/data-center/a100/)
[![Architecture](https://img.shields.io/badge/Architecture-Ampere%20GA100-1f6feb)](#实验平台)
[![CUDA](https://img.shields.io/badge/CUDA-12.4-5c5c5c?logo=nvidia&logoColor=white)](#环境准备)
[![Progress](https://img.shields.io/badge/Selected%20hardware%20scope-complete-2ea44f)](#复现范围与状态)

通过可控微基准、SASS 控制字段修改和真实硬件周期测量，验证现代 NVIDIA GPU Core 的依赖管理、调度、寄存器文件和内存前端行为。

</div>

---

## 项目简介

NVIDIA 没有公开现代 GPU Core 的完整微架构。本项目不依赖性能计数器猜测，而是构造短小、数据结果可验证的 SASS 指令序列，只改变一个控制字段或寄存器映射，然后在 A100 上同时测量：

- `SR_CLOCKLO` 时钟窗口；
- producer-consumer 的最终数据值；
- 非法地址、非法指令等硬件异常；
- 不同 active sub-core 数量下的争用行为。

当前阶段只复现论文中的硬件逆向微基准，不包含 Accel-Sim 实现和最终模拟器误差验证。

## 复现范围与状态

约定的硬件实验范围已经完成。论文第 5.4 节 Table 2 的完整 memory-instruction latency 矩阵被主动跳过，Accel-Sim 建模也不在当前范围内。

| 模块 | 论文位置 | 状态 | A100 结论 |
|---|---|---|---|
| Cubin/SASS 工具链 | Section 3 | 完成 | CUAssembler round-trip 与 Driver API 执行通过 |
| Stall counter | Section 4 / Listing 2 | 完成 | `FADD -> FFMA` 最低正确值为 `S04` |
| Yield 与特殊 stall 编码 | Section 4 | 完成 | `S12-S15, Yield=0` 异常坍缩；`Y:S00` 产生 55-cycle 窗口 |
| Dependence counter | Section 4 | 完成 | `Wn/Bn` 对应关系和 increment visibility 得到验证 |
| `DEPBAR.LE` | Section 4 | 完成 | 自身 Stall 至少为 `S04` 才能正确约束后继指令 |
| CGGTY issue scheduler | Section 5.1 | 完成 | `subcore = hardware_warp_id mod 4`，greedy/youngest 行为得到验证 |
| Instruction front-end | Section 5.2 | 未独立测量 | 当前没有单独的 stream-buffer 容量实验 |
| RF read conflicts | Section 5.3 / Listing 1 | 完成 | 两个 bank，`bank = register_id mod 2` |
| Result queue / bypass | Section 5.3 / Listing 3 | 完成 | fixed-latency consumer 为 4 cycles，LDG 地址消费需 5 cycles |
| Register File Cache | Section 5.3.1 / Listing 4 | 完成 | 命中、消费、保留和同 bank 驱逐得到验证 |
| Memory queue / Table 1 | Section 5.4 / Table 1 | 定性完成 | 5 条连续 LDS 无 backpressure，第 6 条出现拐点 |
| Memory latency / Table 2 | Section 5.4 / Table 2 | 主动跳过 | 未复现完整 load/store、位宽和地址类型矩阵 |
| Accel-Sim 建模与验证 | Sections 6-7 | 不在范围 | 未实现 |

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
| 常规采样 | 20 次预热 + 101 次正式采样 |

## 逆向工作流

```mermaid
flowchart LR
    A[CUDA scaffold] -->|nvcc / ptxas| B[合法 sm_80 cubin]
    B -->|CUAssembler| C[可重新组装的 cuasm]
    C -->|单变量修改| D[实验变体]
    D -->|CUAssembler| E[修改后的 cubin]
    E -->|反汇编审计| F[确认最终 SASS]
    F -->|CUDA Driver API| G[A100 硬件执行]
    G --> H[周期、结果与异常验证]
```

实验遵循以下规则：

1. 同组 cubin 只改变一个控制字段、寄存器编号或 active-warp 数量。
2. 每个变体在运行前都重新反汇编，确认修改进入了最终 SASS。
3. 数据依赖实验同时检查周期和最终结果，不能只看计时。
4. 可能触发 illegal address 的 cubin 使用独立进程运行，避免污染 CUDA context。
5. `cuasm.py cubin -> cuasm` 用于生成可重新组装文件；`dsass.py` 只用于最终人工审计。

## 核心结果

### 1. Stall counter 与固定延迟 RAW

核心窗口：

```sass
CS2R.32 R11, SR_CLOCKLO
NOP
FADD R8, R9, R10        // producer，只改变 Stall
FFMA R12, R8, R8, R8    // consumer
NOP
CS2R.32 R13, SR_CLOCKLO
```

| Stall | Clock delta | consumer 结果 | 分类 |
|---:|---:|---:|---|
| S01 | 6 | 2 | stale |
| S02 | 6 | 2 | stale |
| S03 | 7 | 2 | stale |
| **S04** | **8** | **6** | **首次正确** |
| S05 | 9 | 6 | correct |
| S06 | 10 | 6 | correct |
| S07 | 11 | 6 | correct |
| S08 | 12 | 6 | correct |

`S01-S03` 时 consumer 真实执行并读取旧值，说明测试到的固定延迟 RAW 依赖依靠编译器写入 SASS 的 stall counter，而不是由传统动态 scoreboard 完整兜底。

### 2. Section 4 特殊 control 编码

#### 长 stall 与 Yield

| 变体 | Clock delta | 101 次结果 |
|---|---:|---|
| `DASH_S11` | 15 | 全部正确 |
| `DASH_S12-S15` | 6 | 全部 stale |
| `Y_S11-S15` | 15、16、17、18、19 | 全部正确 |

当 `Stall > 11` 且 `Yield=0` 时，长 stall 异常坍缩；紧随其后的依赖 consumer 读取旧值。该结果与论文描述一致。

#### `Y:S00` 特例

```text
NOP     -:S01 = 2-cycle clock window
ERRBAR  -:S01 = 3-cycle clock window
NOP      Y:S00 = 55-cycle clock window
ERRBAR   Y:S00 = 55-cycle clock window
```

长停顿由 `Yield=1, Stall=0` 的 control encoding 触发，而不是 `ERRBAR` opcode 独有。论文在其测试 GPU 上报告 45 cycles；GA100 的相同计时窗口为 55 cycles，因此这是定性一致、定量不同的结果。

#### `DEPBAR.LE`

```sass
LDG.E R2, ... W2
DEPBAR.LE SB2, 0x0      // 扫描 S01-S05
IADD3 R9, R2, 0x1, RZ  // 无显式 B2 wait
```

| DEPBAR Stall | Median cycles | 分类 |
|---:|---:|---|
| S01 | 10 | 101/101 incorrect |
| S02 | 215 | 101/101 incorrect |
| S03 | 215 | 101/101 incorrect |
| **S04** | **217** | **101/101 correct** |
| S05 | 217 | 101/101 correct |

即使 `S02/S03` 已产生长等待，后继 consumer 仍然错误；`S04` 是第一个正确值，验证论文所述 `DEPBAR.LE` 自身需要至少 Stall 4。

### 3. Dependence counters

```sass
LDG.E ... W2
IADD3 ... B--2---
```

| 变体 | Median cycles | 分类 |
|---|---:|---|
| `dep_CORRECT` | 226 | 101/101 correct |
| `dep_NO_WAIT` | 10 | 101/101 incorrect |
| `dep_WRONG_SB3` | 10 | 101/101 incorrect |

等待错误的 SB3 与完全不等待效果相同。Counter increment 在 producer 发射后的下一周期可见：

| 变体 | Median cycles | 分类 |
|---|---:|---|
| `dep_VIS_S01` | 6 | 101/101 incorrect |
| `dep_VIS_S02` | 213 | 101/101 correct |
| `dep_VIS_Y_S01` | 223 | 101/101 correct |

### 4. Issue scheduler

- `subcore_id = hardware_warp_id mod 4`。
- 无 Yield 时，scheduler 对当前 warp 表现为 greedy。
- 需要切换时，从其他 ready warp 中选择 youngest。
- `Y:S01` 会让出下一 issue opportunity；没有其他 ready warp 时产生一个 bubble。
- `Y:S02` 不会在已有两周期 stall 上机械叠加额外周期。

### 5. Register file 与 RFC

#### RF bank 和读取冲突

```text
bank_id = register_id mod 2
偶数寄存器 -> Bank 0
奇数寄存器 -> Bank 1
```

| 指令序列 | OO | EO | EE |
|---|---:|---:|---:|
| `FFMA -> FFMA` | 6 | 6 | 7 |
| `IADD3 -> FFMA` | 5 | 6 | 7 |

`IADD3 -> FFMA` 对照直接暴露 0、1、2 个 RF read-conflict bubbles。`FFMA -> FFMA` 中连续 FP32 的结构气泡与 RF 气泡重叠。

#### Register File Cache

| 实验 | Clock delta | 结论 |
|---|---:|---|
| `NO_REUSE` | 7 | 普通 RF 读取 |
| `SAME_SLOT_HIT` | 6 | 相同 register、bank、operand slot 命中 |
| `DIFFERENT_SLOT` | 7 | register 相同但 slot 不同，miss |
| `CONSUME` | 9 | 命中后不设置 `.reuse`，entry 被消费 |
| `RETAIN` | 8 | 命中时再次设置 `.reuse`，entry 被保留 |
| `OTHER_BANK` | 8 | 不同 bank 不驱逐原 entry |
| `SAME_BANK` | 10 | 同 bank、同 slot 的其他 register 驱逐原 entry |

### 6. Result queue / bypass

论文 Listing 3 的等价数据流只改变固定延迟 consumer 的 Stall：

```sass
MOV R10, R3        // producer，S04
MOV R3,  R10       // fixed-latency consumer，S04 或 S05
LDG.E R0, [R2.64]  // variable-latency consumer；R2.64 使用 R2:R3 地址对
```

```text
bypass_S04 -> CUDA_ERROR_ILLEGAL_ADDRESS
bypass_S05 -> 32/32 correct，lane 0 = 1000
```

固定延迟 MOV consumer 可以在 4 cycles 时通过 result queue/bypass 获得结果；将该结果作为 variable-latency `LDG` 地址还需要额外一个周期。

### 7. Memory pipeline

#### Table 1 queue 拐点

单 active sub-core：

```text
N00-N05 = 27 cycles
N06     = 30 cycles
N07-N10 = 31、32、33、34 cycles
```

不同 active sub-core 数量均在 `N06` 首次跳变，支持每个 sub-core 为 `4-entry queue + 1 dispatch latch` 的模型。active sub-core 增加后，`N06` 之后的窗口增长更强，验证了共享 memory backend 竞争。当前证据是 prefix-window 的定性复现，不把绝对 delta 直接等同于论文逐指令 issue timestamp。

#### RAW issue-visibility 边界

```text
Shared LDS: D20 stale -> D21 correct，D21 clock window = 38 cycles
Warmed LDG: D28 stale -> D29 correct，D29 clock window = 46 cycles
```

这两个值是 producer-consumer issue-distance 的可见性边界，不是纯 load latency，也不能与端到端 cache/HBM latency直接互换。

## 探索性结果与无效实验

- `05_memory_pipeline/04_global_cache_latency` 的 pointer chase 验证了依赖链和最终索引，但没有严格证明每次访问来自指定缓存层级。
- 早期 64 KiB、1 MiB、8 MiB 对照的编译宏没有生效，程序实际都打印 8 MiB working set，因此该矩阵无效。
- 刷新后的 8 MiB `.cg` 测试约为 969 cycles/load，但不作为 L2 或 HBM latency 写入正式结论。
- Table 2 的 load/store、32/64/128-bit、uniform/regular、constant 和 LDGSTS latency 矩阵未执行。

## 仓库结构

```text
modern-gpu-reproduction/
|-- 00_toolchain/
|-- 01_control_bits/
|   |-- 00_fadd_latency/
|   |-- 01_stall_counter/
|   `-- 02_special_cases/
|-- 02_register_file/
|   |-- 00_read_conflicts/
|   |-- 01_reuse_cache/
|   `-- 02_result_queue_bypass/
|-- 03_scheduler/
|-- 04_dependence_counters/
|-- 05_memory_pipeline/
|-- EXPERIMENT_LOG.md
|-- README.md
`-- env.sh
```

## 环境准备

```bash
cd /root/wym/modern-gpu-reproduction
conda activate cuasm
source env.sh

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=6
export CUAS_HOME=/root/wym/modern-gpu-reproduction/third_party/CuAssembler
export PYTHONPATH="$CUAS_HOME:${PYTHONPATH:-}"
```

常用命令：

```bash
# 完整 cubin -> 可重新组装 cuasm
python "$CUAS_HOME/bin/cuasm.py" input.cubin -o output.cuasm

# cuasm -> cubin
python "$CUAS_HOME/bin/cuasm.py" input.cuasm -o output.cubin

# cubin -> 仅供审计的 SASS
python "$CUAS_HOME/bin/dsass.py" input.cubin -o output.sass
```

## 结果解释边界

- 当前结论只针对 NVIDIA A100 GA100，不默认推广到其他 Ampere、Turing、Hopper 或 Blackwell GPU。
- 控制字段错误可能产生稳定但错误的数据，不能用“kernel 没崩溃”代替正确性验证。
- `needs desc hack` 是 CuAssembler 处理 Ampere descriptor 指令时的已知提示；最终 cubin 仍必须反汇编审计。
- issue-distance、时钟窗口、端到端 latency 和 throughput 是不同指标，文档中不互相替代。
- 本项目不是 NVIDIA 官方架构说明。

## 文档

- [完整实验记录](EXPERIMENT_LOG.md)
- [原论文](https://doi.org/10.1145/3725843.3756064)
- [CUAssembler](https://github.com/cloudcores/CuAssembler)
- [CUDA Binary Utilities](https://docs.nvidia.com/cuda/cuda-binary-utilities/)

---

<div align="center">

**当前阶段：约定的硬件逆向实验范围已完成**  
最后更新：2026-07-24  
维护者：[@Strelizia-zerotwo](https://github.com/Strelizia-zerotwo)

</div>
