from pathlib import Path

source_path = Path("variants/reuse_SAME_SLOT_HIT.cuasm")
output_directory = Path("variants")
source = source_path.read_text(encoding="utf-8")

old_second = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R10, R6, R8 ;"
)

old_nop = (
    "      [B------:R-:W-:-:S01]         /*0080*/"
    "                   NOP ;"
)

second_consume = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R10, R6, R8 ;"
)

second_retain = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R10.reuse, R6, R8 ;"
)

third_probe = (
    "      [B------:R-:W-:-:S01]         /*0080*/"
    "                   IADD3 R9, R10, R6, R8 ;"
)

assert source.count(old_second) == 1
assert source.count(old_nop) == 1

variants = {
    "rfc_CONSUME": second_consume,
    "rfc_RETAIN": second_retain,
}

for name, second_instruction in variants.items():
    variant = source.replace(old_second, second_instruction, 1)
    variant = variant.replace(old_nop, third_probe, 1)

    output_path = output_directory / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
