from pathlib import Path
import re

source_path = Path("baseline/queue_probe_sm80.cuasm")
output_dir = Path("variants")
output_dir.mkdir(parents=True, exist_ok=True)

source_lines = source_path.read_text().splitlines(keepends=True)

control_pattern = re.compile(
    r"\[B[0-5-]{6}:(R[0-5-]):(W[0-5-]):[Y-]:S\d{2}\]"
)

lds_indices = [
    index
    for index, line in enumerate(source_lines)
    if re.search(r"\*/\s+LDS(?:\.|\s)", line)
]

assert len(lds_indices) == 10, (
    f"Expected exactly 10 LDS instructions, found {len(lds_indices)}"
)

def tune_lds(line):
    match = control_pattern.search(line)

    assert match is not None, (
        f"Control field not found on LDS:\n{line}"
    )

    read_barrier = match.group(1)
    write_barrier = match.group(2)

    replacement = (
        f"[B------:{read_barrier}:{write_barrier}:-:S01]"
    )

    result, count = control_pattern.subn(
        replacement,
        line,
        count=1,
    )

    assert count == 1
    return result

def replace_with_nop(line):
    result, count = control_pattern.subn(
        "[B------:R-:W-:-:S01]",
        line,
        count=1,
    )

    assert count == 1, (
        f"Control field not found:\n{line}"
    )

    address_end = result.index("*/") + 2
    prefix = result[:address_end]
    newline = "\n" if line.endswith("\n") else ""

    return f"{prefix}                   NOP ;{newline}"

for load_count in range(11):
    lines = source_lines.copy()

    for position, line_index in enumerate(lds_indices):
        original = source_lines[line_index]

        if position < load_count:
            lines[line_index] = tune_lds(original)
        else:
            lines[line_index] = replace_with_nop(original)

    name = f"queue_N{load_count:02d}"
    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text("".join(lines))

    print(f"{name}: LDS={load_count}, NOP={10 - load_count}")
