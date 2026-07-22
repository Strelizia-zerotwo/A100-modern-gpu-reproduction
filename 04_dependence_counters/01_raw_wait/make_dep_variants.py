from pathlib import Path
import re

source_path = Path("baseline/dep_raw_probe_sm80.cuasm")
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
        f"Expected one instruction at {address_token} "
        f"containing {required_tokens}, found {len(matches)}"
    )

    return matches[0]

indices = {
    "0060": locate_instruction(
        "0060",
        ("LDG",),
    ),
    "0070": locate_instruction(
        "0070",
        ("BAR.SYNC",),
    ),
    "0080": locate_instruction(
        "0080",
        ("IADD3",),
    ),
    "0090": locate_instruction(
        "0090",
        ("CS2R", "SR_CLOCKLO"),
    ),
    "00a0": locate_instruction(
        "00a0",
        ("IMAD.WIDE", "R2"),
    ),
}

wait_mask_pattern = re.compile(r"\[B[0-5-]{6}:")
yield_stall_pattern = re.compile(r":[Y-]:S\d{2}\]")

def set_wait_mask(line, wait_mask):
    result, count = wait_mask_pattern.subn(
        f"[{wait_mask}:",
        line,
        count=1,
    )

    assert count == 1, (
        f"Wait mask not found in:\n{line}"
    )

    return result

def set_yield_stall(line, yield_text, stall):
    result, count = yield_stall_pattern.subn(
        f":{yield_text}:S{stall:02d}]",
        line,
        count=1,
    )

    assert count == 1, (
        f"Yield/Stall field not found in:\n{line}"
    )

    return result

def replace_with_nop(line):
    newline = "\n" if line.endswith("\n") else ""
    address_end = line.index("*/") + 2
    prefix = line[:address_end]

    return f"{prefix}                   NOP ;{newline}"

variants = {
    "dep_CORRECT": "B--2---",
    "dep_NO_WAIT": "B------",
    "dep_WRONG_SB3": "B---3--",
}

for name, consumer_wait_mask in variants.items():
    lines = source_lines.copy()

    # Replace the executable CTA barrier with a fixed SASS NOP.
    lines[indices["0070"]] = replace_with_nop(
        lines[indices["0070"]]
    )
    lines[indices["0070"]] = set_yield_stall(
        lines[indices["0070"]],
        "-",
        1,
    )

    # Consumer: the only field that varies among the three cubins.
    lines[indices["0080"]] = set_wait_mask(
        lines[indices["0080"]],
        consumer_wait_mask,
    )
    lines[indices["0080"]] = set_yield_stall(
        lines[indices["0080"]],
        "-",
        1,
    )

    # Post-clock safety wait before R2 is reused as an output pointer.
    # Keep its original S04 because the following STG consumes R2.
    lines[indices["00a0"]] = set_wait_mask(
        lines[indices["00a0"]],
        "B--2---",
    )

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text("".join(lines))

    print(f"===== {name} =====")
    for address in ("0060", "0070", "0080", "0090", "00a0"):
        print(lines[indices[address]].rstrip())
