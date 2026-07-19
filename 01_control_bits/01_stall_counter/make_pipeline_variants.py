from pathlib import Path

source_path = Path("diagnostic/D_DEP_S01.cuasm")
output_dir = Path("diagnostic")
source = source_path.read_text(encoding="utf-8")

line_0060 = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   FADD R8, R9, R10 ;"
)

line_0070 = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R8, R8, R8 ;"
)

assert source.count(line_0060) == 1
assert source.count(line_0070) == 1

variants = {
    "F_FFMA_ONLY": (
        "      [B------:R-:W-:-:S01]         /*0060*/"
        "                   NOP ;",
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   FFMA R12, R9, R9, R9 ;",
    ),

    "G_TWO_FADD": (
        line_0060,
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   FADD R12, R9, R10 ;",
    ),

    "H_FADD_IADD": (
        line_0060,
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   IADD3 R12, R9, R10, RZ ;",
    ),

    "I_FADD_MOV": (
        line_0060,
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   MOV R12, R9 ;",
    ),
}

for name, (new_0060, new_0070) in variants.items():
    variant = source.replace(line_0060, new_0060, 1)
    variant = variant.replace(line_0070, new_0070, 1)

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
