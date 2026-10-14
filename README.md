# The Calvin Robot Project: Calvin Bench

Calvin is a two-wheeled self-balancing robot with on board AI processing and computer vision. The code for the project is broken into separate repos:

<<<<<<< old
- **Calvin Instinctus**: This Repo. Code for the Teensy 4.1. This provides for Calvin's low level functionality and safety.
- **Calvin Cogitator**: Code that runs on the Jetson. This is Calvin's high level thought.
- **Calvin Explorator**: A native macOS app for monitoring Calvin from a Mac.
- **Calvin Bench**: Tools for analysis, characterization, and debugging of Calvin's systems.
=======
- **Calvin Instinctus**: Code for the Teensy 4.1. This provides for Calvin's low level functionality and safety.
- **Calvin Cogitator**: Code that runs on the Jetson. This is Calvin's high level thought.
- **Calvin Explorator**: A native macOS app for monitoring Calvin from a Mac.
- **Calvin Bench**: This repo. Measures each drive actuator (Teensy → ODrive S1 → motor → belt → wheel) and produces `actuator.yaml`, the input to Calvin's balance controller.
>>>>>>> new

This is a work in progress. 