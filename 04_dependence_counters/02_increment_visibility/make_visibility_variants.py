from pathlib import Path
import re

source_path = Path("baseline/dep_visibility_template.cuasm")
output_dir = Path("variants")
output_dir.mkdir(parents=True, exist_ok=True)

source_lines = source_path.read_text().splitlines(keepends=True)

def locate(address, required_tokens):
    token = f"/*{address}*/"

    matches = [
        index
        for index, line in enumerate(source_lines)
        if token in line
        and all(item in line for item in required_tokens)
    ]

    assert len(matches) == 1, (
        f"Expected one {required_tokens} instruction "
        f"at {token}, found {len(matches)}"
    )

    return matches[0]

indices = {
    "0060": locate("0060", ("LDG",)),
    "0070": locate("0070", ("BAR.SYNC",)),
    "0080": locate("0080", ("IADD3",)),
    "0090": locate("0090", ("CS2R", "SR_CLOCKLO")),
    "00a0": locate("00a0", ("IMAD.WIDE", "R2")),
}

wait_pattern = re.compile(r"\[B[0-5-]{6}:")
yield_stall_pattern = re.compile(r":[Y-]:S\d{2}\]")

def set_wait(line, mask):
    result, count = wait_pattern.subn(
        f"[{mask}:",
        line,
        count=1,
    )
    assert count == 1, f"Wait mask not found:\n{line}"
    return result

def set_yield_stall(line, yield_text, stall):
    result, count = yield_stall_pattern.subn(
        f":{yield_text}:S{stall:02d}]",
        line,
        count=1,
    )
    assert count == 1, f"Yield/Stall field not found:\n{line}"
    return result

def replace_address(line, old_address, new_address):
    old_token = f"/*{old_address}*/"
    new_token = f"/*{new_address}*/"

    assert old_token in line
    return line.replace(old_token, new_token, 1)

def replace_with_nop(line):
    newline = "\n" if line.endswith("\n") else ""
    address_end = line.index("*/") + 2
    prefix = line[:address_end]
    return f"{prefix}                   NOP ;{newline}"

variants = {
    "dep_VIS_S01": ("-", 1),
    "dep_VIS_S02": ("-", 2),
    "dep_VIS_Y_S01": ("Y", 1),
}

for name, (producer_yield, producer_stall) in variants.items():
    lines = source_lines.copy()

    # Move the consumer from 0x0080 to 0x0070 so it is immediately
    # adjacent to the LDG producer at 0x0060.
    consumer_line = replace_address(
        source_lines[indices["0080"]],
        "0080",
        "0070",
    )
    consumer_line = set_wait(consumer_line, "B--2---")
    consumer_line = set_yield_stall(
        consumer_line,
        "-",
        1,
    )
    lines[indices["0070"]] = consumer_line

    # The old consumer slot becomes a fixed spacer NOP.
    lines[indices["0080"]] = replace_with_nop(
        source_lines[indices["0080"]]
    )
    lines[indices["0080"]] = set_yield_stall(
        lines[indices["0080"]],
        "-",
        1,
    )
    lines[indices["0080"]] = set_wait(
        lines[indices["0080"]],
        "B------",
    )

    # Producer: this is the only varying control field.
    lines[indices["0060"]] = set_yield_stall(
        lines[indices["0060"]],
        producer_yield,
        producer_stall,
    )

    # Keep the post-clock safety wait before R2 is overwritten.
    lines[indices["00a0"]] = set_wait(
        lines[indices["00a0"]],
        "B--2---",
    )

    output_path = output_dir / f"{name}.cuasm"
    output_path.write_text("".join(lines))

    print(f"===== {name} =====")
    for address in ("0060", "0070", "0080", "0090", "00a0"):
        print(lines[indices[address]].rstrip())
