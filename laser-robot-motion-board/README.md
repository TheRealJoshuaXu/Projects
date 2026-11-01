# Laser Light Show Robot

ELEC 391, University of British Columbia, Feb–Apr 2024. Team C7, five
people. [← All projects](../README.md)

A two-axis robot that steers a laser to trace shapes. Motors turn the yaw
and pitch axes through printed gearboxes, encoders report position, and a
PID loop on each axis drives the laser to a sequence of target points.

<p>
  <img src="images/robot.jpg" width="60%" alt="The assembled robot with its control board">
  <img src="images/robot-side.jpg" width="36%" alt="Side view of the yaw and pitch stages">
</p>

## My part: the motion control board

I designed the robot's custom multilayer control board in Altium Designer:

- **Motor drive:** a custom H-bridge motor driver.
- **Feedback:** encoder feedback.
- **Power:** on-board regulation.

It carries the microcontroller and the laser output. I built and
commissioned the board, then debugged the faults that only appeared once it
was assembled into the robot and running.

<p>
  <img src="images/board-3d.jpg" width="48%" alt="3D render of the control board">
  <img src="images/board-layout.png" width="48%" alt="Board layout with H-bridge, regulator and programmable logic">
</p>

## The rest of the system (team work)

**Gearboxes.** Gear trains step the motors down on each axis: an
8-tooth pinion driving a 45-tooth gear on yaw, with a 360 CPR encoder, and a
10-tooth pinion driving a 100-tooth gear on pitch, with a 640 CPR encoder.

<img src="images/gear.jpg" width="35%" alt="CAD model of a gearbox gear">

**Quadrature decoding.** The encoder signals are decoded into direction and
count, in hardware logic and in software.

![Quadrature decoder logic](images/quadrature-decoder.png)

**Control.** Each axis was tuned in stages, P → PD → PI → PID. The demo
constants were Kp = 2, Ki = 0.02, Kd = 0.1 on yaw and Kp = 0.1, Ki = 0.01, Kd = 0.01 on pitch.

![Axis position responding to a setpoint step during tuning](images/step-response.png)
*Position (orange) responding to a step in setpoint (blue), captured while
tuning.*

**Drawing shapes.** A shape is stored as a list of (x, y) points on the
projection plane. Each point becomes a target angle on each axis through
θ = atan(coordinate / z), where z is the distance to the plane. The
controller holds each point until the setpoint is reached, then moves to the
next.
