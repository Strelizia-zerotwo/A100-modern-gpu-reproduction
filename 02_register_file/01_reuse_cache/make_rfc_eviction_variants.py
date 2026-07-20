from pathlib import Path

source_path = Path("variants/rfc_CONSUME.cuasm")
output_directory = Path("variants")
source = source_path.read_text(encoding="utf-8")

old_second = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R10, R6, R8 ;"
)

preserve_entry = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R5, R6, R8 ;"
)

evict_entry = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R4, R6, R8 ;"
)

assert source.count(old_second) == 1

variants = {
    # R5 is odd, so it maps to the other bank than cached R10.
    "rfc_OTHER_BANK": preserve_entry,

    # R4 is even, so it maps to the same bank and slot as cached R10.
    "rfc_SAME_BANK": evict_entry,
}

for name, second_instruction in variants.items():
    variant = source.replace(old_second, second_instruction, 1)

    output_path = output_directory / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
