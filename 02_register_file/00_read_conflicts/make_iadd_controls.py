from pathlib import Path

input_dir = Path("variants")
output_dir = Path("control_iadd")
output_dir.mkdir(parents=True, exist_ok=True)

variants = {
    "iadd_OO_R5_R7": input_dir / "bank_OO_R5_R7.cuasm",
    "iadd_EO_R6_R7": input_dir / "bank_EO_R6_R7.cuasm",
    "iadd_EE_R6_R8": input_dir / "bank_EE_R6_R8.cuasm",
}

old_first = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   FFMA R9, R4, R6, R8 ;"
)

new_first = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   IADD3 R9, R4, R6, R8 ;"
)

for name, source_path in variants.items():
    source = source_path.read_text(encoding="utf-8")

    assert source.count(old_first) == 1, (
        f"{source_path}: first FFMA not found exactly once"
    )

    variant = source.replace(old_first, new_first, 1)

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
