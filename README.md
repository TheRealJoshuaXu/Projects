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
| [Underwater Acoustic Energy Harvester](marine-energy-harvester/) | Power management design, layout and validation | Altium Designer, Python |
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

A nickel microheater with an integrated resistance temperature detector,
taken from KLayout through the UBC cleanroom: maskless photolithography,
thermal evaporation with lift-off, PECVD silicon nitride and wet etch. I then
calibrated the RTD (TCR about 7.0 × 10⁻³ per °C), compared it against an
infrared camera, and worked through why the measured resistance was three
times the prediction.

<p>
  <img src="microheater-rtd/images/wafer.jpg" width="40%" alt="Patterned wafer">
  <img src="microheater-rtd/images/temperature-vs-power.png" width="56%" alt="Heater temperature vs power from the RTD and an infrared camera">
</p>

## [45 nm CMOS RF and Analog Blocks](cmos-rf-analog/)

Three circuits designed and simulated in Cadence, sized with the
gm/I<sub>D</sub> method:

- a 5.25 GHz cascode LNA with 18.3 dB gain and a 2.05 dB noise figure
- an LC VCO with −119.0 dBc/Hz phase noise at 1 MHz and an 11.1% tuning range
- a two-stage op-amp with 46.4 dB gain, 692 MHz unity-gain frequency and a
  63.8° phase margin

<p>
  <img src="cmos-rf-analog/images/vco-schematic.png" width="40%" alt="VCO schematic">
  <img src="cmos-rf-analog/images/vco-phase-noise.png" width="56%" alt="VCO phase noise plot">
</p>

## [Underwater Acoustic Energy Harvester](marine-energy-harvester/)

Capstone project, team of five, sponsored through the NATO Science for Peace
and Security programme. The system harvests ship noise through a
piezoelectric transducer to power underwater sensors. I owned the BQ25570
boost converter and power management subsystem: IC selection, threshold
design, layout, a second revision with switchable current sensing, and the
validation plan.

<img src="marine-energy-harvester/images/board-rev2.png" width="70%" alt="JM-111 Rev. 2 board layout">

## [Laser Display Robot Motion Control Board](laser-robot-motion-board/)

A custom multilayer board combining H-bridge motor drive, encoder feedback
and on-board power regulation, built, commissioned and debugged on the
assembled robot.
