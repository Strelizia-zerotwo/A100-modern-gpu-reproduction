from pathlib import Path

source_path = Path("baseline/stall_counter_sm80.original.cuasm")
output_directory = Path("variants")

source = source_path.read_text(encoding="utf-8")

kernel_marker = "  .text.stall_counter_probe:"
kernel_position = source.index(kernel_marker)

instruction_start = source.index("      [", kernel_position)
instruction_end = source.index("  .L_x_1:", instruction_start)

output_directory.mkdir(parents=True, exist_ok=True)

for stall in range(1, 9):
    stall_text = f"S{stall:02d}"

    replacement = f"""\
      [B------:R-:W-:-:S02]         /*0000*/                   IMAD.MOV.U32 R1, RZ, RZ, c[0x0][0x28] ;
      [B------:R-:W-:-:S01]         /*0010*/                   FADD R8, RZ, 1 ;
      [B------:R-:W-:-:S01]         /*0020*/                   FADD R9, RZ, 1 ;
      [B------:R-:W-:-:S02]         /*0030*/                   FADD R10, RZ, 1 ;
      [B------:R-:W-:-:S01]         /*0040*/                   CS2R.32 R11, SR_CLOCKLO ;
      [B------:R-:W-:-:S01]         /*0050*/                   NOP ;
      [B------:R-:W-:-:{stall_text}]         /*0060*/                   FADD R8, R9, R10 ;
      [B------:R-:W-:-:S01]         /*0070*/                   FFMA R12, R8, R8, R8 ;
      [B------:R-:W-:-:S01]         /*0080*/                   NOP ;
      [B------:R-:W-:-:S01]         /*0090*/                   CS2R.32 R13, SR_CLOCKLO ;
      [B------:R-:W0:-:S02]         /*00a0*/                   S2R R0, SR_TID.X ;
      [B0-----:R-:W-:Y:S13]         /*00b0*/                   ISETP.NE.AND P0, PT, R0, RZ, PT ;
      [B------:R-:W-:-:S05]         /*00c0*/               @P0 EXIT ;
      [B------:R-:W-:-:S01]         /*00d0*/                   MOV R2, c[0x0][0x160] ;
      [B------:R-:W-:-:S01]         /*00e0*/                   IMAD.MOV.U32 R3, RZ, RZ, c[0x0][0x164] ;
      [B------:R-:W-:-:S01]         /*00f0*/                   MOV R4, c[0x0][0x168] ;
      [B------:R-:W-:-:S01]         /*0100*/                   IMAD.MOV.U32 R5, RZ, RZ, c[0x0][0x16c] ;
      [B------:R-:W-:-:S01]         /*0110*/                   MOV R6, c[0x0][0x170] ;
      [B------:R-:W-:-:S01]         /*0120*/                   IMAD.MOV.U32 R7, RZ, RZ, c[0x0][0x174] ;
      [B------:R-:W-:-:S02]         /*0130*/                   ULDC.64 UR4, c[0x0][0x118] ;
      [B------:R-:W-:-:S04]         /*0140*/                   STG.E desc[UR4][R2.64], R11 ;
      [B------:R-:W-:-:S04]         /*0150*/                   STG.E desc[UR4][R4.64], R13 ;
      [B------:R-:W-:-:S01]         /*0160*/                   STG.E desc[UR4][R6.64], R12 ;
      [B------:R-:W-:-:S05]         /*0170*/                   EXIT ;
  .L_x_0:
      [B------:R-:W-:Y:S00]         /*0180*/                   BRA `(.L_x_0);
      [B------:R-:W-:Y:S00]         /*0190*/                   NOP;
      [B------:R-:W-:Y:S00]         /*01a0*/                   NOP;
      [B------:R-:W-:Y:S00]         /*01b0*/                   NOP;
      [B------:R-:W-:Y:S00]         /*01c0*/                   NOP;
      [B------:R-:W-:Y:S00]         /*01d0*/                   NOP;
      [B------:R-:W-:Y:S00]         /*01e0*/                   NOP;
      [B------:R-:W-:Y:S00]         /*01f0*/                   NOP;
"""

    variant = source[:instruction_start] + replacement + source[instruction_end:]

    output_path = output_directory / f"stall_{stall_text}.cuasm"
    output_path.write_text(variant, encoding="utf-8")

    print(f"generated {output_path}")
