# Thin-Film Microheater and RTD

ELEC 463 Micro/Nanofabrication Lab, University of British Columbia, Jan–Apr 2026.
[← All projects](../README.md)

A nickel-chromium microheater with an integrated resistance temperature
detector (RTD), designed, fabricated and characterised in the UBC cleanroom.

| | |
| --- | --- |
| **Stack** | 10 nm Cr / 100 nm Ni on SiO2, Si3N4 passivation (100 nm target) |
| **Design** | Serpentine heater with integrated RTD, 20 µm design rules, laid out in KLayout |
| **Tools** | Heidelberg MLA150 maskless aligner, Kurt J. Lesker thermal evaporator, Trion PECVD, Filmetrics reflectometer, infrared camera |

## Process flow

1. **Layout** in KLayout.
2. **Photolithography** on a Heidelberg MLA150 maskless aligner with AZ5214
   resist.
3. **Metal deposition** by thermal evaporation with lift-off, thickness
   monitored by quartz crystal microbalance.
4. **Passivation**: PECVD silicon nitride (silane, ammonia and nitrogen,
   about 300 °C).
5. **Second lithography** to open the contact pads.
6. **Wet nitride etch**, about 300–350 s including a deliberate over-etch.

Deposition and etch times were set from rates calibrated on dummy wafers
(a ~500 s test deposition and a ~100 s test etch), with thickness measured by
reflectometry.

## Results and what they showed

- **Resistance:** the heater measured 256.7 Ω against 83.3 Ω calculated from
  sheet resistance, about three times higher. The likely causes are linewidth
  reduction and edge rounding in the patterned lines, contact resistance, and
  the absence of a dedicated van der Pauw structure to measure the film's
  real sheet resistance.
- **Temperature coefficient of resistance:** about 7.0 × 10⁻³ per °C, higher
  than bulk nickel, consistent with thin-film effects.
- **RTD vs infrared camera:** the integrated RTD read hotter than the camera.
  The difference is explained by emissivity, by the RTD measuring locally
  where the camera sees the surface, and by thermal gradients.
- **Design lesson:** I found that the pad opening window was drawn about the
  same size as the pad itself. It should be larger, to leave alignment
  tolerance between the two lithography steps.
