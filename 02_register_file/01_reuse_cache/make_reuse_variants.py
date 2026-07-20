from pathlib import Path

source_path = Path("baseline/reuse_template.cuasm")
output_directory = Path("variants")
output_directory.mkdir(parents=True, exist_ok=True)

source = source_path.read_text(encoding="utf-8")

old_iadd = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   IADD3 R9, R4, R6, R8 ;"
)

old_ffma = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R10, R6, R8 ;"
)

assert source.count(old_iadd) == 1, (
    "没有唯一找到 0060 位置的 IADD3"
)

assert source.count(old_ffma) == 1, (
    "没有唯一找到 0070 位置的 FFMA"
)

variants = {
    # 控制组：
    # 第一条指令读取 R10，但没有设置 reuse，
    # 第二条 FFMA 必须从普通 Register File 读取 R10。
    "reuse_NO_REUSE": {
        "iadd": (
            "      [B------:R-:W-:-:S01]         /*0060*/"
            "                   IADD3 R9, R10, R5, R7 ;"
        ),
        "ffma": (
            "      [B------:R-:W-:-:S01]         /*0070*/"
            "                   FFMA R12, R10, R6, R8 ;"
        ),
    },

    # 同 slot 命中：
    # IADD3 的 R10 位于 source slot 0，并设置 reuse。
    # FFMA 的 R10 同样位于 source slot 0。
    "reuse_SAME_SLOT_HIT": {
        "iadd": (
            "      [B------:R-:W-:-:S01]         /*0060*/"
            "                   IADD3 R9, R10.reuse, R5, R7 ;"
        ),
        "ffma": (
            "      [B------:R-:W-:-:S01]         /*0070*/"
            "                   FFMA R12, R10, R6, R8 ;"
        ),
    },

    # 不同 slot：
    # IADD3 将 R10 缓存在 source slot 0，
    # 但 FFMA 在 source slot 1 请求 R10。
    "reuse_DIFFERENT_SLOT": {
        "iadd": (
            "      [B------:R-:W-:-:S01]         /*0060*/"
            "                   IADD3 R9, R10.reuse, R5, R7 ;"
        ),
        "ffma": (
            "      [B------:R-:W-:-:S01]         /*0070*/"
            "                   FFMA R12, R6, R10, R8 ;"
        ),
    },
}

for name, instructions in variants.items():
    variant = source.replace(old_iadd, instructions["iadd"], 1)
    variant = variant.replace(old_ffma, instructions["ffma"], 1)

    output_path = output_directory / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
