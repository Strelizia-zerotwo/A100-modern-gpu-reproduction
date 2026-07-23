# NVIDIA A100 GPU Core 微架构逆向复现实验记录

本文记录在 NVIDIA A100（GA100，`sm_80`）上对论文 *Dissecting and Modeling the Architecture of Modern GPU Cores* 所选硬件微基准的复现过程和最终结果。

当前约定范围已经完成。这里的“完成”只指选定的硬件逆向实验，不包括论文第 5.4 节 Table 2 的完整 memory-instruction latency 矩阵、独立的 Section 5.2 stream-buffer/front-end 容量实验、Accel-Sim 实现和模拟器误差验证。

## 1. 实验环境

| 项目 | 配置 |
|---|---|
| 实验日期 | 2026-07-19 至 2026-07-24 |
| GPU | NVIDIA A100-SXM4-40GB |
| 微架构 | Ampere GA100 |
| Compute Capability | 8.0（`sm_80`） |
| SM 数量 | 108 |
| NVIDIA Driver | 550.54.14 |
| CUDA Toolkit | 12.4 |
| 使用的物理 GPU | GPU 6 |
| GPU 隔离 | `CUDA_DEVICE_ORDER=PCI_BUS_ID`、`CUDA_VISIBLE_DEVICES=6` |
| SASS 工具 | CUAssembler、cuobjdump、nvdisasm |
| Cubin 执行 | CUDA Driver API |
| 常规采样 | 20 次预热，101 次正式采样 |

运行环境：

```bash
cd /root/wym/modern-gpu-reproduction
conda activate cuasm
source env.sh

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=6
export CUAS_HOME=/root/wym/modern-gpu-reproduction/third_party/CuAssembler
export PYTHONPATH="$CUAS_HOME:${PYTHONPATH:-}"
```

## 2. 通用方法与证据标准

实验先用 `nvcc/ptxas` 生成合法的 `sm_80` cubin，再用 CUAssembler 生成可重新组装的 cuasm。每组变体只修改一个目标控制字段、寄存器映射或 active-warp 数量，重新组装后直接通过 CUDA Driver API 加载 cubin。

工具的用途严格区分：

```text
cuasm.py cubin -> cuasm    生成完整、可重新组装的 cuasm
cuasm.py cuasm -> cubin    重新组装实验 cubin
dsass.py cubin -> sass     反汇编审计，不作为可重新组装输入
```

每个变体运行前都审计最终 SASS，确认实际编码确实不同。尤其是 Ampere descriptor 指令可能触发 CUAssembler 的 `needs desc hack` 提示，不能只凭源 cuasm 文件名判断修改是否生效。

数据依赖实验同时使用两类证据：

1. `CS2R.32 SR_CLOCKLO` 记录的时钟窗口。
2. producer-consumer 最终数据值，或预期的 illegal-address 行为。

只看周期不足以判断依赖是否正确，因为错误控制字段可能产生稳定、可重复但错误的数据。可能污染 CUDA context 的非法地址变体使用独立 runner 进程执行。

## 3. Control Bits

### 3.1 Stall counter：固定延迟 RAW

对应论文 Section 4 和 Listing 2。核心序列为：

```sass
CS2R.32 R11, SR_CLOCKLO
NOP
FADD R8, R9, R10        // producer，只扫描该指令的 Stall
FFMA R12, R8, R8, R8    // consumer
NOP
CS2R.32 R13, SR_CLOCKLO
```

初始值为 `R8=R9=R10=1`。producer 正确完成后 `R8=2`，因此 consumer 读取新值时得到 `6`，读取旧值时得到 `2`。

| Stall | Min/median/max cycles | 结果 | 分类 |
|---:|---:|---:|---|
| S01 | 6/6/6 | 2 | stale |
| S02 | 6/6/6 | 2 | stale |
| S03 | 7/7/7 | 2 | stale |
| **S04** | **8/8/8** | **6** | **首次正确** |
| S05 | 9/9/9 | 6 | correct |
| S06 | 10/10/10 | 6 | correct |
| S07 | 11/11/11 | 6 | correct |
| S08 | 12/12/12 | 6 | correct |

每种配置的 101 次结果一致。`S01-S03` 时 consumer 真实执行并读到旧值，说明该固定延迟 RAW 依赖需要编译器正确编码 stall counter，硬件没有用传统动态 scoreboard 完整兜底。

对照实验还观察到连续 FP32 warp 指令的一个结构气泡：

```text
A_BASE       NOP -> NOP          5 cycles
B_FADD       FADD -> NOP         5 cycles
F_FFMA_ONLY  NOP -> FFMA         5 cycles
C_INDEP      FADD -> 独立 FFMA   6 cycles
D_DEP_S01    FADD -> 依赖 FFMA   6 cycles
G_TWO_FADD   FADD -> FADD        6 cycles
H_FADD_IADD  FADD -> IADD3       5 cycles
I_FADD_MOV   FADD -> MOV         5 cycles
E_DEP_S04    FADD(S04) -> FFMA   8 cycles
```

因此该序列在 GA100 上的窗口表现为 `max(6, stall_value + 4)`。额外一周期来自测试到的连续 FP32 指令结构限制，不是动态 RAW 保护。

### 3.2 长 Stall 与 Yield 特例

只改变 producer FADD 的 Yield 字段和 Stall，最终反汇编确认实际 control field 已编码到目标地址。

| Yield 字段 | Stall | Clock delta | 101 次结果 |
|---|---:|---:|---|
| `-` | S11 | 15 | 全部 correct |
| `-` | S12 | 6 | 全部 stale |
| `-` | S13 | 6 | 全部 stale |
| `-` | S14 | 6 | 全部 stale |
| `-` | S15 | 6 | 全部 stale |
| `Y` | S11 | 15 | 全部 correct |
| `Y` | S12 | 16 | 全部 correct |
| `Y` | S13 | 17 | 全部 correct |
| `Y` | S14 | 18 | 全部 correct |
| `Y` | S15 | 19 | 全部 correct |

当 `Stall > 11 && Yield=0` 时，长 stall 坍缩为短延迟并导致 consumer 读取旧值；设置 Yield 后 S11-S15 按 15-19 cycles 正常增长。这与论文描述一致。

### 3.3 `Y:S00` 与 ERRBAR

使用 NOP 对照判断特殊延迟来自 control encoding 还是 opcode：

| 变体 | Clock delta | 数据分类 |
|---|---:|---|
| `nop_DASH_S01` | 2 | other=101 |
| `errbar_DASH_S01` | 3 | other=101 |
| `nop_Y_S00` | 55 | other=101 |
| `errbar_Y_S00` | 55 | other=101 |

NOP 与 ERRBAR 在 `Y:S00` 下都产生 55-cycle 窗口，因此长停顿来自 `Yield=1, Stall=0` 的特殊 control encoding，不是 ERRBAR opcode 独有。论文在其测试 GPU 上报告 45 cycles；GA100 的相同计时窗口为 55 cycles，属于定性复现、定量架构差异。

### 3.4 `DEPBAR.LE` 的 Stall 下界

核心数据流：

```sass
LDG.E ... W2
DEPBAR.LE SB2, 0x0      // 扫描 S01-S05
IADD3 R9, R2, 0x1, RZ  // 不显式设置 B2 wait
```

| DEPBAR Stall | Min/median/max cycles | 分类 |
|---:|---:|---|
| S01 | 10/10/10 | correct=0, incorrect=101 |
| S02 | 213/215/382 | correct=0, incorrect=101 |
| S03 | 214/215/382 | correct=0, incorrect=101 |
| **S04** | **216/217/385** | **correct=101, incorrect=0** |
| S05 | 215/217/385 | correct=101, incorrect=0 |

`S02/S03` 虽然已经产生长等待，后继 consumer 仍得到错误结果；`S04` 是第一个正确值。结果精确验证论文所述 `DEPBAR.LE` 自身至少需要 Stall 4。

## 4. Issue Scheduler

13-warp 调度实验确认：

- `subcore_id = hardware_warp_id mod 4`。
- 无 Yield 时，scheduler 对当前 warp 表现为 greedy。
- 需要切换到其他 ready warp 时，选择 youngest ready warp。
- `Y:S01` 会让出下一次 issue opportunity；没有其他 ready warp 时产生一个 bubble。
- `Y:S02` 不会在已有两周期 stall 上机械叠加额外周期。

这些结果支持论文描述的 CGGTY 调度行为。当前项目没有另做 Section 5.2 的 stream-buffer/front-end 容量实验。

## 5. Register File

### 5.1 RF bank 与读冲突

对应论文 Listing 1 和 Section 5.3。实验不设置 `.reuse`，通过改变源寄存器奇偶组合扫描 0、1、2 个 bank conflict。

| 指令序列 | OO | EO | EE |
|---|---:|---:|---:|
| `FFMA -> FFMA` | 6 | 6 | 7 |
| `IADD3 -> FFMA` | 5 | 6 | 7 |

`IADD3 -> FFMA` 的 5/6/7 cycles 直接对应 0/1/2 个 RF read-conflict bubbles。原始 `FFMA -> FFMA` 中，第一个 RF 气泡与连续 FP32 的结构气泡重叠，因此是 6/6/7。

结论：

```text
bank_id = register_id mod 2
偶数寄存器 -> Bank 0
奇数寄存器 -> Bank 1
```

早期使用 R14 的变体触发 `CUDA_ERROR_ILLEGAL_INSTRUCTION`，该变体被舍弃，不作为 bank 结论证据。最终结论只来自低编号寄存器、可稳定执行且最终 SASS 已审计的变体。

### 5.2 Register File Cache

| 实验 | Clock delta | 观察 |
|---|---:|---|
| `NO_REUSE` | 7 | 普通 RF 读取 |
| `SAME_SLOT_HIT` | 6 | 同 register、bank、operand slot 命中 |
| `DIFFERENT_SLOT` | 7 | register 相同但 slot 不同，miss |
| `CONSUME` | 9 | 命中但不再次 `.reuse`，entry 被消费 |
| `RETAIN` | 8 | 命中时再次 `.reuse`，entry 被保留 |
| `OTHER_BANK_2INST` | 6 | 两指令不同 bank 对照 |
| `SAME_BANK_2INST` | 7 | 两指令同 bank 对照 |
| `OTHER_BANK` | 8 | 不同 bank 不驱逐原 entry |
| `SAME_BANK` | 10 | 同 bank、同 slot 的其他 register 驱逐原 entry |

RFC 命中取决于 warp、register ID、register bank 和 source operand slot。命中但不设置 `.reuse` 会消费 entry；命中时再次设置 `.reuse` 会保留 entry；同 bank、同 slot 的其他 register 访问会驱逐原 entry。

三指令 `SAME_BANK - OTHER_BANK = 2 cycles`，其中 1 cycle 来自第二条指令本身的 RF bank conflict，由两指令对照扣除后，剩余 1 cycle 对应第三条 probe 的 RFC miss。

## 6. Dependence Counters

### 6.1 RAW wait 与 scoreboard 编号

```sass
LDG.E ... W2
IADD3 ... B--2---
```

| 变体 | Median cycles | 分类 |
|---|---:|---|
| `dep_CORRECT` | 226 | correct=101 |
| `dep_NO_WAIT` | 10 | incorrect=101 |
| `dep_WRONG_SB3` | 10 | incorrect=101 |

`LDG W2` 的 consumer 必须等待 SB2。等待错误的 SB3 与完全不等待效果相同。

### 6.2 Counter increment visibility

| 变体 | Median cycles | 分类 |
|---|---:|---|
| `dep_VIS_S01` | 6 | incorrect=101 |
| `dep_VIS_S02` | 213 | correct=101 |
| `dep_VIS_Y_S01` | 223 | correct=101 |

相邻 consumer 在 S01 下看到尚未递增的 counter 并逃逸；S02 或 `Y:S01` 提供一个可见性间隔，使 consumer 正确等待 load。结果表明 dependence counter increment 在 producer 发射后的下一周期可见。

## 7. Result Queue / Bypass

对应论文 Listing 3。最终审计的相邻变体只改变 fixed-latency consumer 的 Stall：

```sass
MOV R10, R3        // producer，S04
MOV R3, R10        // fixed-latency consumer，S04 或 S05
LDG.E R0, [R2.64]  // variable-latency consumer；R2.64 使用 R2:R3 地址对
```

| 变体 | 结果 |
|---|---|
| `bypass_S04` | `CUDA_ERROR_ILLEGAL_ADDRESS` |
| `bypass_S05` | lane 0 = 1000，correct=32，incorrect=0 |

固定延迟 MOV consumer 在 4 cycles 时可通过 result queue/bypass 获得 producer 结果；但紧接着把该值作为 variable-latency `LDG` 地址使用需要 5 cycles。S04 的非法地址是实验预期证据，而不是 runner 本身损坏。

## 8. Memory Pipeline

### 8.1 Table 1：Memory instruction queue

使用固定指令槽的 LDS 前缀实验，观察连续 memory instruction 数量增加后的时钟窗口。单 active sub-core 的结果：

```text
N00-N05 = 27 cycles
N06     = 30 cycles
N07     = 31 cycles
N08     = 32 cycles
N09     = 33 cycles
N10     = 34 cycles
```

不同 active sub-core 数量的最终摘要：

```text
active=1: N00-N05=27; N06=30; N07-N10=31,32,33,34
active=2: N00-N05=29/28; N06=32/32; N07-N10=33,34,35,36
active=3: N00-N05=36/35/27; N06=39/39/32; N07-N10 每步约 +2
active=4: N00-N05 约 28-35; N06=38/38/34/34; N07-N10 每步约 +3
```

所有 active-subcore 配置都在 `N06` 出现第一个一致拐点，支持每个 sub-core 的 `4-entry queue + 1 dispatch latch` 模型：5 条连续 LDS 可先被前端吸收，第 6 条开始 backpressure。active sub-core 增加后，拐点后的增长更强，说明它们竞争共享 memory backend。

该证据来自 prefix clock windows，是 Table 1 结构结论的定性复现；不把窗口绝对值冒充为每条 LDS 的精确 issue timestamp。

### 8.2 Shared 与 warmed-global RAW visibility

#### Shared LDS

```text
D03-D20: 结果 1，全部 stale
D21-D27: 结果 1001，全部 correct
D20 clock window = 37 cycles
D21 clock window = 38 cycles
```

#### Warmed global LDG

```text
D04-D28: 结果 1，全部 stale
D29-D36: 结果 1001，全部 correct
D28 clock window = 45 cycles
D29 clock window = 46 cycles
```

这些数值是 producer 发射后，consumer 在多大 issue-distance 下首次能看到新值的边界。它们包含计时框架和指令间隔，不是纯 LDS/LDG load latency，更不是端到端 L2 或 HBM 延迟。

## 9. 探索性 Pointer Chase 与无效矩阵

`05_memory_pipeline/04_global_cache_latency` 的依赖 pointer chase 能验证最终索引，但当前测试没有严格证明每一步来自指定缓存层级。

刷新后 8 MiB `.cg` 的 21 次采样为：

```text
Total cycles: min=7907056 median=7941891 max=7957204
Cycles/load: min=965.217 median=969.469 max=971.338
Validation: correct=21 incorrect=0
```

该约 969 cycles/load 的数值不能标注为 L2 或 HBM latency。早期名为 64 KiB、1 MiB、8 MiB 的对照 cubin 实际都打印 `Working set: 8388608 bytes`，说明编译宏没有进入程序；该矩阵无效，不进入正式结论。

## 10. 最终范围矩阵

| 项目 | 状态 | 最终结论 |
|---|---|---|
| CUAssembler/cubin 工具链 | 完成 | 可生成、修改、重组装并审计 `sm_80` cubin |
| Stall counter | 完成 | `FADD -> FFMA` 首次正确为 S04 |
| 长 Stall/Yield 特例 | 完成 | `Stall>11 && Yield=0` 坍缩，Yield 恢复正常长 stall |
| `Y:S00` 特例 | 完成 | GA100 窗口 55 cycles，机制定性匹配论文 |
| `DEPBAR.LE` | 完成 | 最小正确 Stall 为 S04 |
| Dependence counters | 完成 | W/B 对应及下一周期可见性得到验证 |
| Scheduler | 完成 | sub-core 映射、greedy/youngest、Yield 行为得到验证 |
| RF bank | 完成 | 两个 bank，`register_id mod 2` |
| Register File Cache | 完成 | slot-sensitive hit、consume/retain、bank 驱逐得到验证 |
| Result queue/bypass | 完成 | fixed consumer 4 cycles，LDG 地址消费 5 cycles |
| Memory Table 1 | 定性完成 | N06 拐点支持 4-entry queue + dispatch latch |
| Shared/global RAW visibility | 完成 | D21 与 D29 为首次正确 issue-distance |
| Section 5.2 独立 front-end 容量 | 未执行 | 不作完成声明 |
| Table 2 memory latency matrix | 主动跳过 | 不作 load/store latency 完整复现声明 |
| Pointer-chase cache latency | 探索性 | cache level 未证明，不作正式 latency 结论 |
| Accel-Sim Sections 6-7 | 不在范围 | 未实现、未验证 |

## 11. 最终结论边界

1. 约定的 A100 硬件微基准范围已经完成，但不能表述为“整篇论文完整复现”。
2. 结果只直接适用于本次测试的 GA100；45/55-cycle 等定量差异不能无条件推广到其他架构。
3. issue-distance、时钟窗口、纯指令 latency、端到端 memory latency 和 throughput 是不同指标。
4. Table 2、独立 front-end capacity 和 Accel-Sim 是明确未完成项，不应从当前结果中外推。
5. 所有正式结论均要求最终 SASS 审计和数据正确性证据；未审计的源文件修改、仅文件名不同的 cubin 或 cache level 未证明的 pointer chase 不作为论文复现证据。

最后更新：2026-07-24。
