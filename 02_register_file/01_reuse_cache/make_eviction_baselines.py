from pathlib import Path

input_directory = Path("variants")
output_directory = Path("variants")

sources = {
    "rfc_OTHER_BANK_2INST": (
        input_directory / "rfc_OTHER_BANK.cuasm"
    ),
    "rfc_SAME_BANK_2INST": (
        input_directory / "rfc_SAME_BANK.cuasm"
    ),
}

old_probe = (
    "      [B------:R-:W-:-:S01]         /*0080*/"
    "                   IADD3 R9, R10, R6, R8 ;"
)

final_nop = (
    "      [B------:R-:W-:-:S01]         /*0080*/"
    "                   NOP ;"
)

for name, source_path in sources.items():
    source = source_path.read_text(encoding="utf-8")

    assert source.count(old_probe) == 1, (
        f"{source_path}: 没有唯一找到第三条 probe"
    )

    variant = source.replace(old_probe, final_nop, 1)

    output_path = output_directory / f"{name}.cuasm"
    output_path.write_text(variant, encoding="utf-8")
    print(f"generated {output_path}")
