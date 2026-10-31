# 45 nm CMOS RF and Analog Blocks

Analog CMOS IC Design and RF Integrated Circuits, University of British
Columbia, Dec 2025–Apr 2026. [← All projects](../README.md)

Three circuit blocks designed and simulated at schematic level in a 45 nm
CMOS process using Cadence Virtuoso and Spectre.

| Block | Result |
| --- | --- |
| 5.25 GHz LC voltage-controlled oscillator | −119.0 dBc/Hz phase noise |
| Cascode low-noise amplifier | 2.05 dB noise figure |
| Two-stage operational amplifier | Optional project, used to learn Cadence Virtuoso |

## Notes

- The designs use real industry-supplied on-chip inductor models rather
  than ideal components.
- The op-amp was an optional project and my first use of Cadence Virtuoso; I
  taught myself the tool to do it.
- Scope: schematic design and simulation. No physical layout or post-layout
  extraction was done.
