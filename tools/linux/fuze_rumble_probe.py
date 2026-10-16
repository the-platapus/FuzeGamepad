#!/usr/bin/env python3
"""
Fuze Tomahawk F1 rumble probe (Linux, stdlib only).

The controller's HID descriptor declares no rumble report, but the device has
an interrupt OUT endpoint (EP 0x02). This tool talks to /dev/hidrawN to find
out whether the firmware reacts to any undeclared output/feature report.
Works over USB and Bluetooth. Setup and findings: see README.md next to this file.

Transports:
  int   - USB: raw bytes on the interrupt OUT endpoint (hidraw write)
          BT:  HIDP DATA|OUTPUT on the interrupt channel
  out   - SET_REPORT(Output)  on the control endpoint/channel (HIDIOCSOUTPUT)
  feat  - SET_REPORT(Feature) on the control endpoint/channel (HIDIOCSFEATURE)

Commands:
  info                    show which hidraw node is the controller
  getscan                 read-only: GET_REPORT sweep of report IDs 0..255
  setscan [out|feat]      SET_REPORT with all-zero payloads, logs which IDs the
                          firmware ACKs vs rejects. Both firmwares ACK
                          everything, so this found nothing. Avoid `feat`:
                          feature reports appear to be the pairing path.
  try [transport ...]     pulse a curated list of known rumble formats; you
                          answer y/n for each
  sweep [transport] [pre-hex]
                          pulse [id, FF, FF, ...] for every first byte, in
                          groups of 16, then bisect the group you felt.
                          Optional pre-hex is sent before each group, e.g.
                          `sweep int 01FF` to test with output report 1 set
  values <transport> <hex-prefix> [hex values...]
                          step the byte after <hex-prefix> through values,
                          reading hidden reports back while each is active,
                          e.g.:  values int 01      (hidden BT output report 1)
  send <transport> <hex>  send one report, e.g.:  send int 0951 00ff00ff
"""
import errno
import fcntl
import glob
import os
import sys
import time

TARGETS = {("0003", "00000079", "0000181C"): "USB",
           ("0005", "000012D1", "0000A560"): "Bluetooth"}


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


def HIDIOCSFEATURE(n): return _ioc(3, 0x06, n)
def HIDIOCGFEATURE(n): return _ioc(3, 0x07, n)
def HIDIOCGINPUT(n):   return _ioc(3, 0x0A, n)
def HIDIOCSOUTPUT(n):  return _ioc(3, 0x0B, n)
def HIDIOCGOUTPUT(n):  return _ioc(3, 0x0C, n)


def find_node():
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(path, "device/uevent")) as f:
                env = dict(l.strip().split("=", 1) for l in f if "=" in l)
        except OSError:
            continue
        key = tuple(env.get("HID_ID", "::").upper().split(":"))
        key = (key[0].lower().zfill(4),) + key[1:]
        if key in TARGETS:
            return "/dev/" + os.path.basename(path), TARGETS[key], env.get("HID_NAME", "?")
    return None, None, None


# usbhid strips a leading 0x00 from hidraw writes, hidp (Bluetooth) does not.
WIRE_PREFIX = b"\x00"
# The controller's L2CAP MTU is the 48-byte minimum (1 byte goes to the HIDP
# header). An oversized write makes BlueZ drop the whole HID device.
MAX_LEN = 64
# Seconds between interrupt writes. BlueZ drops the HID device if the
# Bluetooth link backs up, so writes over BT must be paced.
PACE = 0.0


def open_dev():
    global WIRE_PREFIX, MAX_LEN, PACE
    node, kind, name = find_node()
    if not node:
        sys.exit("Controller not found (expected 0079:181C over USB or 12D1:A560 over BT).")
    try:
        fd = os.open(node, os.O_RDWR)
    except PermissionError:
        sys.exit(f"No permission for {node}. Install the udev rule from tools/linux/README.md, then reconnect.")
    WIRE_PREFIX = b"\x00" if kind == "USB" else b""
    MAX_LEN = 64 if kind == "USB" else 47
    PACE = 0.0 if kind == "USB" else 0.02
    return fd, node, kind, name


def hx(b):
    return " ".join(f"{x:02X}" for x in b)


def send(fd, transport, report):
    """report = [report_id, payload...]. Returns None on success, else an error string."""
    report = bytes(report)
    if len(report) > MAX_LEN:
        return f"skipped, longer than {MAX_LEN}"
    try:
        if transport == "int":
            # On USB the prefix puts `report` on the wire byte-for-byte,
            # even when report[0] is 0.
            os.write(fd, WIRE_PREFIX + report)
            time.sleep(PACE)
        elif transport == "out":
            fcntl.ioctl(fd, HIDIOCSOUTPUT(len(report)), bytearray(report))
        elif transport == "feat":
            fcntl.ioctl(fd, HIDIOCSFEATURE(len(report)), bytearray(report))
        else:
            raise ValueError(transport)
        return None
    except OSError as e:
        if e.errno == errno.ENODEV:
            sys.exit("\n!!! Controller disconnected. Nothing after this point was delivered; reconnect and rerun.")
        return {errno.EPIPE: "STALL", errno.ETIMEDOUT: "TIMEOUT"}.get(e.errno, e.strerror)


# ---------------------------------------------------------------- candidates
# Wire formats used by other cheap / clone controllers that Linux drives.
# Each entry: (name, [on messages], [off messages]). All "on" values are max.
def pad(b, n):
    return list(b) + [0] * (n - len(b))


CANDIDATES = [
    ("current repo attempt: [02 small big]",           [[0x02, 0xFF, 0xFF]],                       [[0x02, 0x00, 0x00]]),
    ("report 02 padded to input size (10)",            [pad([0x02, 0xFF, 0xFF], 10)],              [pad([0x02], 10)]),
    ("LED report 04 all bits",                         [[0x04, 0x1F]],                             [[0x04, 0x00]]),
    ("LED report 04 0xFF",                             [[0x04, 0xFF]],                             [[0x04, 0x00]]),
    ("DragonRise/GreenAsia (hid-dr, hid-gaff) 7B",     [[0x51, 0x00, 0xFF, 0x00, 0xFF, 0x00, 0x00],
                                                        [0xFA, 0xFE, 0x00, 0x00, 0x00, 0x00, 0x00]],
                                                                                                   [[0xF3, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]]),
    ("DragonRise 8B",                                  [pad([0x51, 0x00, 0xFF, 0x00, 0xFF], 8),
                                                        pad([0xFA, 0xFE], 8)],                     [pad([0xF3], 8)]),
    ("DragonRise with report ID 0",                    [pad([0x00, 0x51, 0x00, 0xFF, 0x00, 0xFF], 8),
                                                        pad([0x00, 0xFA, 0xFE], 8)],               [pad([0x00, 0xF3], 8)]),
    ("Xbox 360 wired [00 08 00 big small]",            [[0x00, 0x08, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0x00]],
                                                                                                   [[0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]]),
    ("Xbox One GIP rumble (4 motors) seq0",            [[0x05, 0x20, 0x00, 0x01, 0x00],
                                                        [0x09, 0x00, 0x00, 0x09, 0x00, 0x0F, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xFF]],
                                                                                                   [[0x09, 0x00, 0x01, 0x09, 0x00, 0x0F, 0, 0, 0, 0, 0, 0, 0]]),
    ("Xbox One GIP rumble, no power-on",               [[0x09, 0x00, 0x02, 0x09, 0x00, 0x0F, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xFF]],
                                                                                                   [[0x09, 0x00, 0x03, 0x09, 0x00, 0x0F, 0, 0, 0, 0, 0, 0, 0]]),
    ("DS3-style report 01",                            [pad([0x01, 0x00, 0xFF, 0x01, 0xFF, 0xFF], 49)],
                                                                                                   [pad([0x01], 49)]),
    ("DS4-style report 05",                            [pad([0x05, 0x07, 0x00, 0x00, 0xFF, 0xFF], 32)],
                                                                                                   [pad([0x05, 0x07], 32)]),
    ("EMS-style [01 01 weak strong]",                  [pad([0x01, 0x01, 0xFF, 0xFF], 8)],         [pad([0x01, 0x01], 8)]),
    ("ACRUX-style 4 bytes no ID",                      [[0x00, 0xFF, 0xFF, 0xFF, 0xFF]],           [[0x00, 0x00, 0x00, 0x00, 0x00]]),
    ("generic [03 big small]",                         [pad([0x03, 0xFF, 0xFF], 8)],               [pad([0x03], 8)]),
    ("generic [05 big small]",                         [pad([0x05, 0xFF, 0xFF], 8)],               [pad([0x05], 8)]),
    ("4-motor guess [ID 02..06, FF x4]",               [pad([i, 0xFF, 0xFF, 0xFF, 0xFF], 8) for i in range(2, 7)],
                                                                                                   [pad([i], 8) for i in range(2, 7)]),
]


def pulse(fd, transport, on, off, seconds=1.2, quiet=False):
    errs = set()
    end = time.time() + seconds
    while True:
        for msg in on:
            e = send(fd, transport, msg)
            if e:
                errs.add(f"{hx(msg[:3])}..:{e}")
        if time.time() >= end:
            break
        time.sleep(0.1)
    for msg in off:
        send(fd, transport, msg)
    if errs and not quiet:
        print("    errors:", "; ".join(sorted(errs)[:4]))
    return errs


def ask(prompt):
    while True:
        a = input(prompt).strip().lower()
        if a in ("y", "n", "r", "q"):
            return a


# ---------------------------------------------------------------- commands
def cmd_info():
    node, kind, name = find_node()
    print(node, kind, name) if node else print("not found")


def cmd_getscan():
    fd, node, kind, _ = open_dev()
    print(f"GET_REPORT sweep on {node} ({kind}). Read-only.")
    for label, ioc in (("feature", HIDIOCGFEATURE), ("input", HIDIOCGINPUT), ("output", HIDIOCGOUTPUT)):
        answers = {}
        for rid in range(256):
            buf = bytearray([rid] + [0] * 64)
            try:
                n = fcntl.ioctl(fd, ioc(len(buf)), buf, True)
                answers.setdefault(bytes(buf[:n]), []).append(rid)
            except OSError:
                pass
        print(f"\n{label}: {sum(map(len, answers.values()))} report IDs answered")
        for data, ids in answers.items():
            span = f"{len(ids)} IDs" if len(ids) > 8 else " ".join(f"{r:02X}" for r in ids)
            print(f"  [{span}] -> {hx(data)}")
    os.close(fd)


def cmd_setscan(transport="out"):
    fd, node, kind, _ = open_dev()
    print(f"SET_REPORT({transport}) sweep with zero payloads on {node} ({kind}).")
    for length in (2, 8, 16, 64):
        acked = [rid for rid in range(1, 256) if send(fd, transport, [rid] + [0] * (length - 1)) is None]
        print(f"  len {length:2}: ACKed {len(acked)}/255  " +
              (" ".join(f"{r:02X}" for r in acked) if len(acked) < 40 else "(firmware ACKs nearly everything)"))
    os.close(fd)


def cmd_try(transports):
    fd, node, kind, _ = open_dev()
    print(f"Probing {node} ({kind}). Hold the controller. Answer y = felt it, n = nothing, r = repeat, q = quit.\n")
    found = []
    for transport in transports:
        for name, on, off in CANDIDATES:
            while True:
                print(f"[{transport}] {name}")
                pulse(fd, transport, on, off)
                a = ask("    felt rumble? [y/n/r/q] ")
                if a != "r":
                    break
            if a == "q":
                break
            if a == "y":
                found.append((transport, name))
        else:
            continue
        break
    print("\nHits:" if found else "\nNo hits.")
    for t, n in found:
        print(f"  {t}: {n}")
    os.close(fd)


def cmd_sweep(transport="int", pre_hex=""):
    fd, node, kind, _ = open_dev()
    lengths = (2, 3, 5, 8, 9, 13, 16, 32, 64) if kind == "USB" else (2, 3, 5, 9, 13, 16, 32, 47)
    pre = list(bytes.fromhex(pre_hex))
    print(f"Sweeping first byte 00..FF with FF payloads, lengths {lengths}, transport {transport}" +
          (f", after [{hx(pre)}]." if pre else "."))
    print("Each group takes a few seconds. Answer y = felt it, n = nothing, q = quit.\n")

    def run(ids):
        if pre:
            send(fd, transport, pre)
        on = [[i] + [0xFF] * (n - 1) for i in ids for n in lengths]
        off = [[i] + [0x00] * (n - 1) for i in ids for n in lengths]
        # One paced pass over BT already takes seconds; USB repeats for 2 s.
        errs = pulse(fd, transport, on, off, seconds=2.0 if kind == "USB" else 0, quiet=True)
        if errs:
            print(f"    {len(errs)} sends failed, e.g. {sorted(errs)[0]}")

    for start in range(0, 256, 16):
        group = list(range(start, start + 16))
        print(f"group {start:02X}..{start + 15:02X}")
        run(group)
        a = ask("    felt rumble? [y/n/q] ")
        if a == "q":
            break
        if a == "y":
            while len(group) > 1:
                half = group[: len(group) // 2]
                print(f"  bisect: {half[0]:02X}..{half[-1]:02X}")
                run(half)
                group = half if ask("    felt rumble? [y/n] ") == "y" else group[len(group) // 2:]
            print(f"\n>>> First byte 0x{group[0]:02X} triggers rumble via {transport}. Now narrow the length with:")
            print(f"    send {transport} {group[0]:02X}FF   (then add FF bytes until it buzzes)")
            break
    os.close(fd)


def readback(fd):
    """GET the hidden Bluetooth reports; changes here mean the write did something."""
    out = []
    for label, ioc, rid in (("out01", HIDIOCGOUTPUT, 1), ("in01", HIDIOCGINPUT, 1),
                            ("in03", HIDIOCGINPUT, 3), ("in05", HIDIOCGINPUT, 5),
                            ("feat72", HIDIOCGFEATURE, 0x72)):
        buf = bytearray([rid] + [0] * 16)
        try:
            n = fcntl.ioctl(fd, ioc(len(buf)), buf, True)
            out.append(f"{label}={buf[1:n].hex()}")
        except OSError:
            out.append(f"{label}=--")
    return " ".join(out)


def cmd_values(transport, prefix_hex, values_hex):
    fd, node, kind, _ = open_dev()
    prefix = list(bytes.fromhex(prefix_hex))
    values = [int(v, 16) for v in values_hex] or \
        [0x01, 0x02, 0x04, 0x08, 0x0F, 0x10, 0x20, 0x40, 0x80, 0x7F, 0xF0, 0xFF]
    print(f"Stepping [{hx(prefix)} vv] via {transport} on {node} ({kind}).")
    print(f"baseline: {readback(fd)}")
    print("Hold the controller. y = felt it, n = nothing, r = repeat, q = quit.\n")
    hits = []
    for v in values:
        while True:
            send(fd, transport, prefix + [v])
            time.sleep(0.1)
            during = readback(fd)
            pulse(fd, transport, [prefix + [v]], [prefix + [0]], seconds=1.5)
            print(f"[{hx(prefix + [v])}]  during: {during}")
            a = ask("    felt rumble? [y/n/r/q] ")
            if a != "r":
                break
        if a == "q":
            break
        if a == "y":
            hits.append(v)
    send(fd, transport, prefix + [0])
    print(f"\nafter:    {readback(fd)}")
    print("Hits: " + (" ".join(f"{v:02X}" for v in hits) if hits else "none"))
    os.close(fd)


def cmd_send(transport, hexstr):
    fd, *_ = open_dev()
    data = bytes.fromhex(hexstr.replace(" ", ""))
    e = send(fd, transport, data)
    print(f"{transport} {hx(data)} -> {e or 'OK'}")
    os.close(fd)


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "info":
        cmd_info()
    elif cmd == "getscan":
        cmd_getscan()
    elif cmd == "setscan":
        cmd_setscan(*args[:1])
    elif cmd == "try":
        cmd_try(args or ["int", "out", "feat"])
    elif cmd == "sweep":
        cmd_sweep(*args[:2])
    elif cmd == "values" and len(args) >= 2:
        cmd_values(args[0], args[1], args[2:])
    elif cmd == "send" and len(args) >= 2:
        cmd_send(args[0], "".join(args[1:]))
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print()
