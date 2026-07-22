from pathlib import Path
import re

source_path = Path("baseline/yield_template_sm80.cuasm")
output_dir = Path("variants")
output_dir.mkdir(parents=True, exist_ok=True)

source_lines = source_path.read_text().splitlines(keepends=True)

target_indices = [
    index
    for index, line in enumerate(source_lines)
    if "/*0060*/" in line and "NOP" in line
]

assert len(target_indices) == 1, (
    "Expected exactly one NOP at address 0x0060, "
    f"found {len(target_indices)}"
)

target_index = target_indices[0]
target_line = source_lines[target_index]

control_pattern = re.compile(r":[Y-]:S\d{2}\]")

variants = {
    "yield_DASH_S01": ("-", 1),
    "yield_Y_S01": ("Y", 1),
    "yield_DASH_S02": ("-", 2),
    "yield_Y_S02": ("Y", 2),
}

for name, (yield_text, stall) in variants.items():
    output_lines = source_lines.copy()

    replacement = f":{yield_text}:S{stall:02d}]"

    new_line, replacement_count = control_pattern.subn(
        replacement,
        target_line,
        count=1,
    )

    assert replacement_count == 1, (
        f"Could not replace Yield/Stall field in target line:\n"
        f"{target_line}"
    )

    output_lines[target_index] = new_line

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text("".join(output_lines))

    print(f"{name}:")
    print(f"  {target_line.rstrip()}")
    print(f"  {new_line.rstrip()}")
    print(f"  -> {output_path}")
