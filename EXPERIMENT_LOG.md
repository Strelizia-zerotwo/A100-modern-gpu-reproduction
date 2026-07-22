# NVIDIA A100 GPU 微架构逆向复现实验记录

## 1. 实验环境

- 实验日期：2026-07-19 至 2026-07-20
- GPU：NVIDIA A100-SXM4-40GB
- GPU 微架构：GA100，Ampere
- Compute Capability：8.0，sm_80
- SM 数量：108
- NVIDIA Driver：550.54.14
- CUDA Toolkit：12.4
- 使用的物理 GPU：GPU 6
- GPU 隔离方式：`CUDA_VISIBLE_DEVICES=6`
- SASS 修改工具：CUAssembler
- NVIDIA 工具：nvcc、ptxas、cuobjdump、nvdisasm
- Cubin 执行方式：CUDA Driver API
- 每种配置采样次数：101

## 2. 通用逆向方法

实验首先通过 nvcc/ptxas 生成合法的 sm_80 cubin，再使用 CUAssembler 将 cubin 反汇编为包含控制字段的 cuasm。

在 cuasm 中手工修改目标 SASS 指令、寄存器编号或控制位，再重新组装为 cubin。最后使用 CUDA Driver API 直接加载和执行修改后的 cubin，避免 nvcc 和 ptxas重新优化、重排或修复手写指令。

计时窗口使用两条 `CS2R.32 SR_CLOCKLO`：

```sass
CS2R.32 R_start, SR_CLOCKLO
NOP
待测试指令
NOP
CS2R.32 R_stop, SR_CLOCKLO
周期计算方式：
clock_delta = stop_clock - start_clock
每个变体保持相同的指令地址、窗口长度和非目标控制字段，只改变一个实验变量。每种配置执行 20 次预热和 101 次正式采样。
3. 实验一：Stall Counter
3.1 对应论文内容
论文第 4 节：Control Bits in Modern NVIDIA GPU Architectures
论文 Listing 2：Code to analyze Stall counters behavior
3.2 实验目的
验证 A100 对固定延迟算术 RAW 依赖的处理机制：
producer FADD 产生新的目标寄存器值；
consumer FFMA 紧随其后读取该寄存器；
人为减小 producer 的 stall counter；
观察硬件是否自动检测 RAW hazard；
同时检查周期和最终计算结果。
如果存在完整的动态 RAW scoreboard，即使 stall counter 设置错误，硬件也应阻止 FFMA 读取未准备好的寄存器。
如果硬件依赖编译器编码的 stall counter，那么 stall 不足时 FFMA 将读取旧值并产生错误结果。
3.3 核心 SASS
FADD R8, RZ, 1
FADD R9, RZ, 1
FADD R10, RZ, 1

CS2R.32 R11, SR_CLOCKLO
NOP
FADD R8, R9, R10
FFMA R12, R8, R8, R8
NOP
CS2R.32 R13, SR_CLOCKLO
目标 FADD：
FADD R8, R9, R10
consumer：
FFMA R12, R8, R8, R8
初始值：
R8  = 1
R9  = 1
R10 = 1
FADD 正确完成后：
R8 = R9 + R10 = 2
FFMA 正确读取新 R8 时：
R12 = 2 * 2 + 2 = 6
FFMA 过早读取旧 R8 时：
R12 = 1 * 1 + 1 = 2
因此：
结果 2：读取到旧值
结果 6：读取到正确的新值
3.4 Stall 扫描结果
Stall	最小周期	中位数	最大周期	结果	分类
S01	6	6	6	2	stale
S02	6	6	6	2	stale
S03	7	7	7	2	stale
S04	8	8	8	6	correct
S05	9	9	9	6	correct
S06	10	10	10	6	correct
S07	11	11	11	6	correct
S08	12	12	12	6	correct

每种配置的 101 次采样完全一致。
3.5 结论
S04 是该 FADD -> FFMA 依赖的最小正确 stall。
S01-S03 时，FFMA 实际执行并读取旧寄存器值，没有被硬件动态 scoreboard 完整拦截。这证明该固定延迟 RAW 依赖依靠编译器写入 SASS 的 stall counter 保证正确性。
3.6 与论文的周期差异
论文报告：
S01 = 5 cycles，结果错误
S04 = 8 cycles，结果正确
A100 实测：
S01 = 6 cycles，结果错误
S04 = 8 cycles，结果正确
为定位额外的一周期，进行了以下控制实验：
变体	核心序列	周期
A_BASE	NOP -> NOP	5
B_FADD	FADD -> NOP	5
F_FFMA_ONLY	NOP -> FFMA	5
C_INDEP	FADD -> 独立 FFMA	6
D_DEP_S01	FADD -> 依赖 FFMA	6
G_TWO_FADD	FADD -> FADD	6
H_FADD_IADD	FADD -> IADD3	5
I_FADD_MOV	FADD -> MOV	5
E_DEP_S04	FADD(S04) -> 依赖 FFMA	8

控制实验排除了：
CS2R 计时框架开销；
单条 FADD 开销；
单条 FFMA 开销；
RAW 依赖造成的动态等待；
连续任意非 NOP 指令的通用限制。
额外周期只在测试的连续 FP32 指令之间出现。A100 的完整周期规律为：
clock_delta = max(6, stall_value + 4)
该额外周期是 FP32 执行通路的结构性限制，不是 RAW scoreboard 保护。
4. 实验二：Register File Read Conflicts
4.1 对应论文内容
论文第 3 节：Reverse Engineering Methodology
论文 Listing 1：Code used to check Register File read conflicts
论文第 5.3 节：Register File
4.2 实验目的
通过改变源寄存器编号的奇偶组合，测量连续指令读取寄存器时是否发生不同程度的冲突，从而推断：
register file bank 数量；
register 到 bank 的映射；
每种组合产生的读取气泡数。
实验不启用 reuse bit，避免 Register File Cache 掩盖真实 RF 读取冲突。
4.3 原始 FFMA -> FFMA 实验
第一条 FFMA 使用三个偶数源寄存器：
FFMA R9, R4, R6, R8
第二条 FFMA 保持第一个源寄存器为偶数，只改变后两个源寄存器：
// OO
FFMA R12, R10, R5, R7

// EO
FFMA R12, R10, R6, R7

// EE
FFMA R12, R10, R6, R8
结果：
组合	周期
OO	6
EO	6
EE	7

EE 比 OO 多一个周期，证明寄存器奇偶分布会改变指令时序，存在 bank-sensitive 的读取冲突。
但 OO 和 EO 都是 6，原因是 A100 连续 FP32 指令自身已有一个结构气泡，掩盖了 EO 的第一个 RF 气泡。
4.4 IADD3 -> FFMA 对照
为了移除连续 FP32 指令的结构限制，将第一条 FFMA 替换为三源 IADD3：
IADD3 R9, R4, R6, R8
第二条 FFMA 的寄存器组合保持不变。
结果：
组合	最小周期	中位数	最大周期	RF 气泡
OO	5	5	5	0
EO	6	6	6	1
EE	7	7	7	2

该结果与论文 Listing 1 的 5/6/7 cycles 完全一致。
4.5 Bank 映射结论
实验支持两个普通寄存器 bank，其映射与寄存器编号奇偶一致：
bank_id = register_id mod 2
即：
偶数寄存器 -> Bank 0
奇数寄存器 -> Bank 1
4.6 FP32 气泡与 RF 气泡的重叠
原始 FFMA -> FFMA 序列的总气泡不是两种气泡简单相加，而是等待所有资源同时可用：
实际气泡 = max(FP32 pipeline 气泡, RF bank 气泡)
组合	FP32 气泡	RF 气泡	实际气泡	总周期
OO	1	0	1	6
EO	1	1	1	6
EE	1	2	2	7

这解释了：
FFMA -> FFMA：6/6/7
IADD3 -> FFMA：5/6/7
4.7 被舍弃的 R14 变体
最初使用：
FFMA R9, R8, R10, R14
运行时触发：
CUDA_ERROR_ILLEGAL_INSTRUCTION
隔离实验结果：
J_FIRST_ONLY：仅执行该 FFMA，仍然 illegal
K_SECOND_ONLY：执行 FFMA R12,R4,R5,R7，正常，5 cycles
随后将实验改为不超过 R12 的低编号寄存器，非法指令消失。
R14 失败的准确原因尚未确定，可能涉及模板 cubin 的寄存器分配元数据或 CUAssembler 编码边界。因此该失败只记录为被舍弃的实验变体，不作为寄存器 bank 结论的证据。
5. 当前已确认结论
A100 对测试的固定延迟算术 RAW 依赖使用编译器编码的 stall counter。
FADD -> FFMA 的最小正确 stall 为 S04。
S01-S03 会使 consumer 读取旧寄存器值并产生错误结果。
A100 上测试的连续 FP32 warp 指令存在一个结构性气泡。
普通寄存器堆表现出两个 bank。
bank 映射与 register_id mod 2 一致。
OO、EO、EE 分别产生 0、1、2 个 RF 读取冲突气泡。
FP32 结构限制与 RF 读取限制会重叠，不一定简单相加。
6. 下一步
下一项计划复现论文第 5.3.1 节 Register File Cache：
source operand reuse bit；
RFC 命中与失效；
operand slot 匹配；
bank 和 operand position 对 RFC 的影响；
Listing 4 的四种 cache 行为。

## 实验三：Register File Cache 与 reuse bit

### 3.1 对应论文内容

- 论文第 5.3.1 节：Register File Cache
- 论文 Listing 4：Register File Cache behavior

### 3.2 相同 operand slot 的命中

实验序列：

```sass
IADD3 R9, R10.reuse, R5, R7
FFMA  R12, R10,       R6, R8
结果：
变体	Clock delta
reuse_NO_REUSE	7
reuse_SAME_SLOT_HIT	6
reuse_DIFFERENT_SLOT	7

R10 在第一条指令中位于 source slot 0。第二条 FFMA 在 source slot 0 使用 R10 时命中 RFC；当 R10 移到 source slot 1 时，即使 register ID 相同，也会 miss。
这证明 RFC 命中不仅依赖寄存器编号，还依赖 operand slot。
3.3 Consume 与 Retain
三条指令：
IADD3 R9,  R10.reuse, R5, R7
FFMA  R12, R10[.reuse], R6, R8
IADD3 R9,  R10,       R6, R8
结果：
变体	Clock delta	行为
rfc_CONSUME	9	第二条命中但未保留，第三条 miss
rfc_RETAIN	8	第二条命中并再次设置 .reuse，第三条继续 hit

因此：
CONSUME - RETAIN = 9 - 8 = 1 cycle
这复现了论文 Listing 4 的 Example 1 和 Example 2。
3.4 Bank 相关的驱逐
两条指令基线：
变体	Clock delta
rfc_OTHER_BANK_2INST	6
rfc_SAME_BANK_2INST	7

三条指令版本：
变体	Clock delta
rfc_OTHER_BANK	8
rfc_SAME_BANK	10

两指令版本的差异：
7 - 6 = 1 cycle
它来自第二条 FFMA 自身的寄存器 bank 读取冲突。
三指令版本的总差异：
10 - 8 = 2 cycles
扣除第二条指令自身的差异后：
2 - 1 = 1 cycle
这个额外周期来自 RFC entry 被驱逐：
R10 位于 Bank 0、source slot 0

OTHER_BANK：
第二条 source slot 0 使用奇数寄存器 R5
R5 属于 Bank 1
R10 的 Bank 0、slot 0 entry 保留
第三条 R10 命中

SAME_BANK：
第二条 source slot 0 使用偶数寄存器 R4
R4 与 R10 属于同一个 Bank
同 bank、同 slot 的访问驱逐 R10
第三条 R10 miss
这复现了论文 Listing 4 的 Example 3 和 Example 4。
3.5 RFC 实验结论
A100 上的 RFC 行为符合以下模型：
命中条件：
- 同一个 warp
- 相同 register ID
- 相同 register bank
- 相同 source operand slot
- RFC entry 尚未被消费或驱逐
生命周期：
命中但不设置 .reuse
    -> entry 被消费
    -> 下一次访问 miss

命中且再次设置 .reuse
    -> entry 被保留
    -> 下一次访问仍可 hit
驱逐规则：
不同 bank、相同 slot
    -> 不驱逐原 entry

相同 bank、相同 slot 的其他寄存器
    -> 驱逐原 entry
注意：当前 RFC 生命周期实验没有在最后一条 probe 和 CS2R 之间增加 final NOP。由于比较是在完全相同的窗口内进行的，差分结果仍然稳定；后续如需比较绝对周期，将重建带 final NOP 的规范计时窗口。

<!-- LOG_2026_07_22 -->
## 2026-07-22：调度器、依赖计数器与 Memory Pipeline

### CGGTY warp scheduler

13 个 warp（416 threads）实验确认 `subcore_id = hardware_warp_id mod 4`。无 Yield 时 sample span 为 20 cycles，所有 warp 的 start-to-stop 均为 3 cycles，同 sub-core 内高 hardware warp ID 优先并 greedy 执行。启用 Yield 后 span 为 21 cycles，其他 ready warp 会插入当前 warp 的 start/stop 区间。

### Dependence counter RAW wait

```text
dep_CORRECT:   median=226 cycles，correct=101/101
dep_NO_WAIT:   median=10 cycles， incorrect=101/101
dep_WRONG_SB3: median=10 cycles， incorrect=101/101
LDG W2 的 consumer 必须使用 B--2---。等待错误的 SB3 与完全不等待效果相同。
Dependence counter increment visibility
dep_VIS_S01:   median=6 cycles，   incorrect=101/101
dep_VIS_S02:   median=213 cycles， correct=101/101
dep_VIS_Y_S01: median=223 cycles， correct=101/101
结论：counter increment 在 producer 发射后的下一周期才可见。相邻 consumer 在 S01 下看到旧的零值并逃逸；S02 或 Y:S01 提供一个可见性间隔，使 consumer 正确等待 load 完成。
Memory instruction queue
单 sub-core、固定 10 个指令槽：
N00-N05: 27 cycles
N06:     30 cycles
N07-N10: 31、32、33、34 cycles
N10:     correct=101/101
四 sub-core 同时活跃时的最小值：
N00-N05: 33 cycles
N06-N10: 36、39、42、45、48 cycles
结论：每个 sub-core 可无阻塞接受 5 条连续 LDS，第 6 条出现 backpressure，符合“4-entry queue + 1-entry dispatch latch”模型。四 sub-core 的队列拐点相同，但队列填满后出现稳定的共享后端竞争。
