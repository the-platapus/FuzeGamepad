# Rumble research (Linux)

The Tomahawk F1 controller has 4 vibration motors (2 in the grips, 2 in the
triggers), but no OS has ever made them move. These notes record what the
controller exposes and what has been tried, so nobody has to repeat it.

**Status:** no software command that drives the motors has been found over USB
or Bluetooth, and the test controller has never vibrated on its own, not even
at power-up or pairing. The next step is hardware (see the end of this doc).

## Setup

`fuze_rumble_probe.py` needs only Python 3. To let your user open the
controller's raw HID node without root:

```bash
sudo cp tools/linux/70-fuze-gamepad.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
```

Reconnect the controller, then run `python3 tools/linux/fuze_rumble_probe.py`
for the command list.

## Identity

| | USB | Bluetooth |
|---|---|---|
| VID:PID | `0079:181C` (DragonRise) | `12D1:A560` (Huawei) |
| Name | `Fuze game` / `usb controller` | `Fuze game controller` |
| Endpoints | EP 0x81 IN, **EP 0x02 OUT** (interrupt, 64 B) | L2CAP MTU 48 (see below) |

The console it shipped with ran Fuze OS (Android) on a Tegra K1.

## HID descriptor

Same on both transports, only the collection order differs.

| Report | Direction | Size | Contents |
|---|---|---|---|
| `0x02` | Input | 10 B | 16 buttons, hat, X/Y/Z/Rz, 2 analog triggers (Simulation C4/C5) |
| `0x04` | Input | 9 B | Keyboard modifiers, consumer keys, 6-key array |
| `0x04` | Output | 2 B | 5 keyboard LED bits |

There are **no feature reports** and no rumble/PID usages. On Windows this means
the only report HidLibrary can write is `[04 xx]`; `WriteFeatureData([02 ..])`
always fails.

## USB firmware

Every GET_REPORT request, of any type and any report ID, returns the
controller's own Bluetooth address (`4C FF 12 C0 1C 3C` on the test unit).
Every SET_REPORT is ACKed. The USB side looks like a pairing responder plus the
wired gamepad, similar to how a DualShock 3 is paired over USB.

## Bluetooth firmware

The Bluetooth stack validates report IDs on GET_REPORT, which reveals reports the
descriptor doesn't declare (`getscan`):

| Type | ID | Value read | Notes |
|---|---|---|---|
| Output | `01` | `00` (1 B) | **Hidden.** Stores any byte written over either channel and reads it back. No visible or felt effect for any value tested |
| Input | `01` | `00 × 8` | Hidden. Never changed |
| Input | `02` | `00 × 4` | Shorter than the declared 10 B input report |
| Input | `03` | `D7` + own BT address | Hidden |
| Input | `04` | `00` | |
| Input | `05` | `02` | Hidden. Maybe battery level or version |
| Feature | `72` | `00 00 00 00 00 00 8E` | Hidden. Possibly pairing/config storage. **Not written to** |
| Output | `04` | error | The declared LED report is rejected on GET |

SET_REPORT is accepted for every ID, so it gives no signal.

**Gotchas when sending over Bluetooth (BlueZ userspace HID):**
- Writes longer than 47 bytes (MTU 48 minus the HIDP header) fail with
  `Message too long`, and BlueZ then removes the HID device while the radio link
  stays up. The controller looks connected in GNOME but has no hidraw node.
  Fix: `bluetoothctl disconnect <addr>`, then press the Fuze button.
- Writing faster than the link drains gives `Output queue is full`, followed by
  the same silent teardown. The probe paces Bluetooth writes at 20 ms.
- The host can't start the connection; the controller has to (Fuze button).

## What was tried (all negative)

| Test | USB | Bluetooth |
|---|---|---|
| `try`: 17 known formats (DragonRise `51 00 / FA FE`, Xbox 360 `00 08`, Xbox One GIP `09` incl. trigger motors, DS3 `01`, DS4 `05`, EMS, ACRUX, LED report, `[02 small big]`, generic `[id FF..]`), sent as `int`, `out` and `feat` | ✗ | ✗ (`int`, `out`) |
| `values`: hidden output `01` = 01, 02, 04, 08, 0F, 10, 20, 40, 80, 7F, F0, FF | n/a | ✗ (`int`, `out`) |
| `sweep`: every first byte 00..FF with FF payloads, lengths 2–47/64 | not run | ✗ |
| `sweep int 01FF`: same, with output `01` = FF first | n/a | ✗ |

Not ruled out: commands that need a multi-byte magic value, a checksum or an
init handshake. These are impractical to brute-force by feel.

## Next: hardware

1. Check the motors: with the controller off, put ~3 V (2×AA) across a motor's
   leads.
2. Check the driver circuit: each motor should have a small transistor/MOSFET
   and a flyback diode. Empty pads mean rumble was cut at the factory.
3. If the driver parts are fitted, trace the transistor's gate/base to the chip
   pin that drives it.
4. Fallback that works regardless of firmware: a small add-on microcontroller
   drives the 4 motors, and the Windows app forwards the rumble values it
   already receives from the virtual Xbox 360 bus.
