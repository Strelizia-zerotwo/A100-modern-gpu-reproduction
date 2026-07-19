
## 已验证的 A100 实验结果

### 实验环境

- GPU：NVIDIA A100-SXM4-40GB，GA100，计算能力 8.0
- CUDA Toolkit：12.4
- GPU 隔离：物理 GPU 6，使用 `CUDA_VISIBLE_DEVICES=6`
- SASS 修改工具：CUAssembler
- 反汇编工具：cuobjdump、nvdisasm
- Cubin 执行方式：CUDA Driver API
- 每种实验配置采样 101 次

### 实验一：Stall Counter 与固定延迟 RAW 依赖

该实验对应论文第 4 节以及 Listing 2。我们改变 producer `FADD` 的 stall counter，并让紧随其后的 `FFMA` 立即读取 `FADD` 的目标寄存器。

| Stall | 时钟差 | FFMA 结果 | 解释 |
|---:|---:|---:|---|
| S01 | 6 | 2 | 读取到旧寄存器值 |
| S02 | 6 | 2 | 读取到旧寄存器值 |
| S03 | 7 | 2 | 读取到旧寄存器值 |
| S04 | 8 | 6 | 读取到正确的新值 |
| S05 | 9 | 6 | 读取到正确的新值 |
| S06 | 10 | 6 | 读取到正确的新值 |
| S07 | 11 | 6 | 读取到正确的新值 |
| S08 | 12 | 6 | 读取到正确的新值 |

正确性的临界值为 S04，与论文 Listing 2 一致。S01-S03 会使 consumer 读取旧数据，说明对于该固定延迟算术 RAW 依赖，硬件不会使用传统动态 scoreboard 自动等待，而是依赖编译器编码在 SASS 中的 stall counter。

A100 上的周期规律为：

```text
clock_delta = max(6, stall_value + 4)
控制实验表明，6-cycle 下限来自连续 FP32 warp 指令之间的一个结构性气泡，与 RAW 依赖保护无关。
实验二：寄存器堆读取冲突
该实验对应论文 Listing 1 和第 5.3 节。实验关闭 operand reuse，只改变第二条指令源寄存器的奇偶组合。
指令序列	奇/奇 OO	偶/奇 EO	偶/偶 EE
FFMA -> FFMA	6	6	7
IADD3 -> FFMA	5	6	7

IADD3 -> FFMA 对照实验消除了 A100 连续 FP32 指令固有的结构性气泡，直接观察到 0、1、2 个寄存器读取冲突气泡。结果支持两个寄存器 bank，以及如下奇偶映射：
bank_id = register_id mod 2
在原始 FFMA -> FFMA 序列中，第一个寄存器读取冲突气泡与 A100 的 FP32 结构气泡重叠，因此测得 6/6/7，而不是论文直接观察到的 5/6/7。
完整实验过程、失败变体、控制实验和结论见 [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md)。
当前进度

CUDA、cuobjdump、nvdisasm 工具链验证

CUAssembler cubin -> cuasm -> cubin 往返验证

Stall counter 与固定延迟 RAW 依赖

连续 FP32 指令结构限制定位

Register File bank conflict

Register File Cache 与 reuse bit

Yield bit

Read/Write barrier 与 wait mask

Warp scheduler 时间线

Memory pipeline

Instruction front-end
本阶段只进行真实硬件逆向实验，暂不进行 Accel-Sim 集成和最终仿真误差分析。
