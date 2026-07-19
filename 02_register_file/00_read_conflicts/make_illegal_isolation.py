from pathlib import Path

source_path = Path("variants/bank_OO_R5_R7.cuasm")
output_dir = Path("variants")
source = source_path.read_text(encoding="utf-8")

first_ffma = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   FFMA R9, R8, R10, R14 ;"
)

second_ffma = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R4, R5, R7 ;"
)

nop_0060 = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   NOP ;"
)

nop_0070 = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   NOP ;"
)

assert source.count(first_ffma) == 1
assert source.count(second_ffma) == 1

variants = {
    "J_FIRST_ONLY": (
        first_ffma,
        nop_0070,
    ),
    "K_SECOND_ONLY": (
        nop_0060,
        second_ffma,
    ),
}

for name, (instruction_0060, instruction_0070) in variants.items():
    variant = source.replace(first_ffma, instruction_0060, 1)
    variant = variant.replace(second_ffma, instruction_0070, 1)

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
