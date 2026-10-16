(Translated to English)
# Tomahawk F1 Controller Driver

Strictly speaking, this is not a driver. It is simply a key-mapping tool. The Tomahawk F1 controller was deliberately designed to deviate from standard Android and XInput controller layouts, which causes the button mappings to be incorrect when used directly on Android or Windows. Additionally, the Windows platform does not support linear input for the triggers (LT, RT).

This tool is modified from the following project:
[https://github.com/irungentoo/Xiaomi_gamepad](https://github.com/irungentoo/Xiaomi_gamepad)

It uses SCP as a driver to emulate an Xbox 360 controller.

# Implemented Features:

> Bluetooth Support

# Features Not Yet Implemented:

> Rumble

# Rumble Research:

The controller has 4 vibration motors, but neither its USB nor its Bluetooth HID descriptor declares a rumble report. Probing both firmwares found hidden Bluetooth reports (including a 1-byte output report `0x01`), but no command that moves the motors. The controller also never vibrates on its own. The board itself has all 4 motor driver circuits fitted, so the hardware is there; the firmware just never switches it on.

Findings, test results and a Linux probe tool are in [tools/linux](tools/linux/README.md).

# About the Controller Design Details:

Please refer to:
[https://github.com/mumumusuc/FuzeController](https://github.com/mumumusuc/FuzeController)
