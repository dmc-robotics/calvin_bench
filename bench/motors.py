"""The drive units: each motor by the CAN node ID its ODrive S1 is configured with (backups in odrive/), and the belt
between motor and wheel."""
NODE_IDS = {"left": 1, "right": 2}
BELT_RATIO = 4.0  # motor turns per wheel turn
