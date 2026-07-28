#!/usr/bin/env python3
"""Synthetic test for NMEA2000 fast-packet reassembly in XanbusMessage.

Proves the 3-bit-sequence / 5-bit-frame split reassembles a >16-frame message
(the PGN 0x1F0BE case) and that the sequence-integrity check is safe once the
split is correct -- and shows the old 4/4 nibble split trips that same check at
frame 16.

Note: this exercises the reassembly *logic* on synthesised frames. It does not
claim to prove that a real Conext 0x1F0BE uses the 3/5 split — only that IF it is
standard NMEA2000 fast-packet (which >16 frames requires, since 4 bits cannot
index past 16), the code handles it correctly.

Run: python3 test_fastpacket_reassembly.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "berrybms"))
from XanbusMessage import XanbusMessage  # noqa: E402


class Frame:
    """Minimal stand-in for the CAN frame object append_bytes() consumes."""
    def __init__(self, data):
        self.data = data


def encode_fastpacket(payload, seq):
    """Encode payload as standard NMEA2000 fast-packet frames.
    control byte = (seq << 5) | frame_index; frame 0 carries the length."""
    frames = [bytes([(seq << 5) | 0, len(payload)]) + payload[:6]]
    pos, idx = 6, 1
    while pos < len(payload):
        chunk = payload[pos:pos + 7]
        chunk = chunk + bytes([0xFF]) * (7 - len(chunk))       # pad like the bus
        frames.append(bytes([(seq << 5) | (idx & 0x1F)]) + chunk)
        pos += 7
        idx += 1
    return frames


def reassemble_ref(frames, shift, mask):
    """Faithful re-implementation of XanbusMessage's reassembly (with the
    sequence check enabled), parameterised by the split, so we can compare the
    3/5 split against the 4/4 nibble split on identical frames.
    Returns (payload_or_None, is_bogus)."""
    data, total, seq_id = None, 0, None
    for f in frames:
        b0 = f[0]
        seq, fid = b0 >> shift, b0 & mask
        if fid == 0 and data is None:
            seq_id, total, data = seq, f[1], bytearray(f[2:])
        else:
            if data is None:
                return None, True
            if seq_id != seq:                 # the integrity check
                return None, True
            data += f[1:]
        if data is not None and len(data) >= total:
            return bytes(data[:total]), False
    return None, False                        # never completed


def main():
    # 150-byte payload -> 1 + ceil((150-6)/7) = 22 frames (> 16, the 1f0be case).
    payload = bytes((i * 7 + 3) & 0xFF for i in range(150))
    frames = encode_fastpacket(payload, seq=3)
    assert len(frames) > 16, f"test needs >16 frames, got {len(frames)}"
    print(f"payload={len(payload)}B -> {len(frames)} frames (>16)")

    # (1) berrybms's actual XanbusMessage (patched 3/5 split, check enabled)
    msg = XanbusMessage(0x1F0BE, src=1, dst=255, pri=6)
    for f in frames:
        msg.append_bytes(Frame(f))
    assert msg.is_ready, "XanbusMessage never completed the >16-frame message"
    assert not msg.is_bogus, "XanbusMessage wrongly flagged it bogus"
    assert msg.bytes()[:len(payload)] == payload, "reassembled payload mismatch"
    print("PASS: XanbusMessage (3/5) reassembles the 22-frame message correctly")

    # (2) same frames, standard 3/5 reference -> completes cleanly
    out, bogus = reassemble_ref(frames, shift=5, mask=0x1F)
    assert out == payload and not bogus
    print("PASS: 3/5 reference completes and matches payload")

    # (3) same frames, old 4/4 nibble reference -> trips the integrity check
    #     (sequence id flips at frame 16), so it does NOT reassemble.
    out, bogus = reassemble_ref(frames, shift=4, mask=0x0F)
    assert out != payload, "nibble split unexpectedly reassembled >16 frames"
    print(f"PASS: 4/4 nibble reference fails on the same frames (bogus={bogus})")

    # (4) regression: a small <=16-frame message still reassembles under 3/5
    small = bytes(range(40))                  # 1 + ceil((40-6)/7) = 6 frames
    sframes = encode_fastpacket(small, seq=5)
    m2 = XanbusMessage(0x1F0C4, src=0, dst=255, pri=6)   # BattSts2
    for f in sframes:
        m2.append_bytes(Frame(f))
    assert m2.is_ready and not m2.is_bogus and m2.bytes()[:len(small)] == small
    print("PASS: <=16-frame message still reassembles (no regression)")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
