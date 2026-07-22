from pathlib import Path
import re

source_path = Path("baseline/cggty_probe_sm80.cuasm")
output_dir = Path("variants")
output_dir.mkdir(parents=True, exist_ok=True)

source_lines = source_path.read_text().splitlines(keepends=True)

def locate_instruction(address, required_tokens):
    address_token = f"/*{address}*/"

    matches = [
        index
        for index, line in enumerate(source_lines)
        if address_token in line
        and all(token in line for token in required_tokens)
    ]

    assert len(matches) == 1, (
        f"Expected exactly one instruction at {address_token} "
        f"containing {required_tokens}, found {len(matches)}"
    )

    return matches[0]

indices = {
    "0030": locate_instruction(
        "0030",
        ("CS2R", "SR_CLOCKLO"),
    ),
    "0040": locate_instruction(
        "0040",
        ("BAR.SYNC",),
    ),
    "0050": locate_instruction(
        "0050",
        ("BAR.SYNC",),
    ),
    "0060": locate_instruction(
        "0060",
        ("CS2R", "SR_CLOCKLO"),
    ),
}

control_pattern = re.compile(r":[Y-]:S\d{2}\]")

def set_control(line, yield_text, stall):
    replacement = f":{yield_text}:S{stall:02d}]"

    result, count = control_pattern.subn(
        replacement,
        line,
        count=1,
    )

    assert count == 1, (
        "Yield/Stall control field not found in:\n"
        f"{line}"
    )

    return result

def replace_with_nop(line):
    newline = "\n" if line.endswith("\n") else ""
    address_end = line.index("*/") + 2
    prefix = line[:address_end]

    return f"{prefix}                   NOP ;{newline}"

variants = {
    "cggty_NO_YIELD": "-",
    "cggty_YIELD": "Y",
}

for name, target_yield in variants.items():
    lines = source_lines.copy()

    # Normalize all four instructions to no-Yield, S01.
    for address in ("0030", "0040", "0050", "0060"):
        index = indices[address]
        lines[index] = set_control(lines[index], "-", 1)

    # Replace only the two executable BAR instructions with NOP.
    lines[indices["0040"]] = replace_with_nop(
        lines[indices["0040"]]
    )
    lines[indices["0050"]] = replace_with_nop(
        lines[indices["0050"]]
    )

    # Only the target NOP at 0x0040 varies.
    lines[indices["0040"]] = set_control(
        lines[indices["0040"]],
        target_yield,
        1,
    )

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text("".join(lines))

    print(f"===== {name} =====")
    for address in ("0030", "0040", "0050", "0060"):
        print(lines[indices[address]].rstrip())
