from pathlib import Path

source_path = Path("variants/stall_S01.cuasm")
output_dir = Path("diagnostic")
output_dir.mkdir(parents=True, exist_ok=True)

source = source_path.read_text(encoding="utf-8")

old_fadd = (
    "      [B------:R-:W-:-:S01]         /*0060*/"
    "                   FADD R8, R9, R10 ;"
)

old_ffma = (
    "      [B------:R-:W-:-:S01]         /*0070*/"
    "                   FFMA R12, R8, R8, R8 ;"
)

assert source.count(old_fadd) == 1, "target FADD not found exactly once"
assert source.count(old_ffma) == 1, "target FFMA not found exactly once"

variants = {
    # Only the measurement frame remains.
    "A_BASE": {
        "fadd": (
            "      [B------:R-:W-:-:S01]         /*0060*/"
            "                   NOP ;"
        ),
        "ffma": (
            "      [B------:R-:W-:-:S01]         /*0070*/"
            "                   NOP ;"
        ),
    },

    # Add only the producer FADD.
    "B_FADD": {
        "fadd": old_fadd,
        "ffma": (
            "      [B------:R-:W-:-:S01]         /*0070*/"
            "                   NOP ;"
        ),
    },

    # Producer plus an independent FFMA.
    "C_INDEP": {
        "fadd": old_fadd,
        "ffma": (
            "      [B------:R-:W-:-:S01]         /*0070*/"
            "                   FFMA R12, R9, R9, R9 ;"
        ),
    },

    # The current dependent S01 experiment.
    "D_DEP_S01": {
        "fadd": old_fadd,
        "ffma": old_ffma,
    },

    # The current dependent S04 experiment.
    "E_DEP_S04": {
        "fadd": (
            "      [B------:R-:W-:-:S04]         /*0060*/"
            "                   FADD R8, R9, R10 ;"
        ),
        "ffma": old_ffma,
    },
}

for name, replacement in variants.items():
    variant = source.replace(old_fadd, replacement["fadd"], 1)
    variant = variant.replace(old_ffma, replacement["ffma"], 1)

    path = output_dir / f"{name}.cuasm"
    path.write_text(variant, encoding="utf-8")
    print(f"generated {path}")
