# Joshua Xu — Engineering Projects

Electrical engineering graduate (BASc, University of British Columbia, 2026).
I work on how hardware is made, tested and qualified: process control,
semiconductor fabrication, power electronics and failure investigation.

[LinkedIn](https://www.linkedin.com/in/joshuaxuubc)

| Project | Area | Tools |
| --- | --- | --- |
| [SPC Analysis Toolkit](spc-toolkit/) | Statistical process control, DOE, AI-assisted analysis | Python, SciPy, MCP |
| [Thin-Film Microheater and RTD](microheater-rtd/) | Cleanroom fabrication and characterisation | KLayout, maskless lithography, PECVD |
| [45 nm CMOS RF and Analog Blocks](cmos-rf-analog/) | IC design and simulation | Cadence Virtuoso, Spectre |
| [Marine Renewable Energy Harvester](marine-energy-harvester/) | Power subsystem design, bring-up and validation | Altium Designer |
| [Laser Display Robot Motion Control Board](laser-robot-motion-board/) | Mixed-signal PCB design and commissioning | Altium Designer |

---

## [SPC Analysis Toolkit](spc-toolkit/)

Ask a production dataset questions in plain English and get statistics you
can audit. Nine statistical process control tools (control limits, Western
Electric rules, Cp/Cpk, two-level factorial DOE, correlation, drift-vs-step
trend testing, windowed yield, charting) exposed to Claude Code over MCP. The
model chooses which analyses to run; every number comes from deterministic,
unit-tested Python.

Validated against faults planted at known values: 32 of 32 checks and 48 unit
tests pass. The DOE recovered a planted +8 temperature effect as +7.65 and a
+3 interaction as +2.64.

<p>
  <img src="spc-toolkit/docs/images/step_change.png" width="49%" alt="Control chart with a step change detected at run 70">
  <img src="spc-toolkit/docs/images/doe_effects.png" width="49%" alt="DOE effects recovered compared with planted values">
</p>

## [Thin-Film Microheater and RTD](microheater-rtd/)

A nickel-chromium microheater with an integrated resistance temperature
detector, taken from layout through fabrication to measurement in the UBC
cleanroom: maskless photolithography, thermal evaporation with lift-off,
PECVD silicon nitride and wet etch. Measured resistance came out about three
times the value calculated from sheet resistance, and the write-up works
through why.

## [45 nm CMOS RF and Analog Blocks](cmos-rf-analog/)

A 5.25 GHz LC oscillator (−119.0 dBc/Hz phase noise), a cascode low-noise
amplifier (2.05 dB noise figure) and a two-stage op-amp, designed and
simulated in Cadence with industry-supplied on-chip inductor models.

## [Marine Renewable Energy Harvester](marine-energy-harvester/)

Capstone project, team of five, sponsored through the NATO Science for Peace
and Security programme. I owned the power subsystem from load budget and
converter topology through schematic, multilayer layout and bench bring-up,
and wrote the validation plan.

## [Laser Display Robot Motion Control Board](laser-robot-motion-board/)

A custom multilayer board combining H-bridge motor drive, encoder feedback
and on-board power regulation, built, commissioned and debugged on the
assembled robot.
