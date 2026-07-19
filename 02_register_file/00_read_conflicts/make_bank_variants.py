from pathlib import Path

source_path = Path("baseline/register_bank_template.cuasm")
output_dir = Path("variants")
output_dir.mkdir(parents=True, exist_ok=True)

source = source_path.read_text(encoding="utf-8")

old_0060 = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   FADD R8, R9, R10 ;"
)

old_0070 = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R8, R8, R8 ;"
)

assert source.count(old_0060) == 1, "instruction 0060 not found exactly once"
assert source.count(old_0070) == 1, "instruction 0070 not found exactly once"

first_ffma = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   FFMA R9, R4, R6, R8 ;"
)

variants = {
    # R5 and R7 are both odd.
    "bank_OO_R5_R7": (
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   FFMA R12, R10, R5, R7 ;"
    ),

    # R6 is even; R7 is odd.
    "bank_EO_R6_R7": (
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   FFMA R12, R10, R6, R7 ;"
    ),

    # R6 and R14 are both even.
    "bank_EE_R6_R8": (
        "      [B------:R-:W-:-:S01]         /*0070*/"
        "                   FFMA R12, R10, R6, R8 ;"
    ),
}

for name, second_ffma in variants.items():
    variant = source.replace(old_0060, first_ffma, 1)
    variant = variant.replace(old_0070, second_ffma, 1)

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
