# Field notes: berrybms layouts vs a Conext SW 4024 + MPPT 60 150 installation

Validation of berrybms's Xanbus decoding against a different hardware mix than
the author's: **Conext SW 4024** inverter (865-4024-21) + **MPPT 60 150**
(865-1030-1), 24 V battery bank, with ground truth from the same site's
InsightHome Modbus registers. Summarized here so the results can flow upstream.

## 1. MPPT 60 150 sends a 21-byte DcSrcSts2 — `processDcSrcSts2` would crash

`XanbusSniffer.processDcSrcSts2` unpacks a fixed 27-byte layout
(`struct.unpack('<BBIii13x', bytes)`). The MPPT 60 150 emits a **21-byte**
reassembled payload for PGN 0x1F0C5, so `struct.unpack` raises `struct.error`
on every PV/battery DC message from this device. (The author's larger MPPT —
which populates longer payloads — is unaffected.) A `struct.unpack_from` or a
length guard fixes it; the meaningful fields sit in the first 14 bytes either
way.

## 2. The MPPT 60 150 does not report PV-side current/power at all

On this model the `assoc 0x15` (PV input) message carries a valid PV **array
voltage** at offset 2, but the current (offset 6) and power (offset 10) fields
are **hard zeros on the wire** — verified during active production (134 W /
5 A delivered to battery, raw payload
`0315 5eec0000 00000000 00000000 0000 fffffffffc0000`). The InsightHome's own
Modbus PV-current registers read zero as well, so this is a hardware/firmware
limitation of the MPPT 60 150, not a decode issue. Solar production for this
model must be read from the **`assoc 0x03` DC-output channel** (which is
self-consistent: V×I=W holds).

## 3. Cross-validation of the core layouts (independent installation)

Confirmed against InsightHome Modbus ground truth on this site:

| PGN | Field | Result |
|---|---|---|
| 0x1F0C4 BattSts2 | V u32@2 ÷1000 | matches Modbus battery V, **r = +0.98**, medians within 0.02 V |
| 0x1F0C5 assoc 0x15 | PV V u32@2 ÷1000 | matches Modbus PV-V mirror (u32 mV pair), same dawn ramp |
| 0x1F0C5 assoc 0x03 (MPPT) | I s32@6, P s32@10 | internally consistent (V×I=W) through a 0→134 W ramp |
| 0x1F00E ChgSts | chg_mode u16@13 | 769/770/773 track Modbus charge-stage register exactly |
| 0x1F0BD InvSts2 | status u16@2 | 1024/1025 as documented |

So the layouts hold across at least two independent installations and two
device generations (XW+ family vs SW 4024).

## 4. Information-content survey of the undecoded PGNs

Byte-position variance over a full day of traffic on this bus — useful for
prioritizing future decoding (a byte that never changes carries no signal):

| PGN | Distinct payloads | Varying byte positions | Note |
|---|---|---|---|
| 0x1F01D (127005) | 49 | bytes 2–3 only | a single u16; everything else static |
| 0x1F00F (126991) | 2 | byte 4 only | a flag/heartbeat bit |
| 0x1F0BF (127167) | 1 | none | constant |
| 0x1F0C9 (127177) | 1 | none | constant |
| 0x1F0C6 SpsSts | 2 | byte 2 (changed once) | ~constant |
| 0x1F0BE (127166) | 157 | @0, 19, 23, 46, 50, 58 (of 60) | the real remaining content |

## 5. 0x1F0BE (127166): labels for the varying fields

The InsightHome Modbus map for the MPPT 60 150 exposes cumulative **Wh energy
counters** (regs 131/135/139/143 — all incremented by the same +115 Wh across
one morning of production) and **operating-second counters** (regs 133/137).
These are the natural labels for 0x1F0BE's varying byte positions via
correlation. Note 0x1F0BE is a **>16-frame fast-packet**, so it requires the
standard 3-bit/5-bit control-byte split to reassemble (see PR #3).

---
*Site details: 2× Prolific RS485, gs_usb CAN adapter, 250 kbit/s, nodes
src0 = SW 4024, src1 = MPPT 60 150. Happy to share capture excerpts on request.*
