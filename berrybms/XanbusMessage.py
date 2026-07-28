#
# Copyright (C) 2025 Extrafu <extrafu@gmail.com>
#
# This file is part of BerryBMS.
#
# BerryBMS is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3, or (at your option) any
# later version.
#
class XanbusMessage(object):

    xanbus_fast_packets = {
        0x1F016, # XW+ / AcStsRms
        0x1F0C5, # XW+/MPPT / DcSrcSts2
        0x1F0C4, # XW+/MPPT / BattSts2
        0x1F0C6, # XW+/MPPT / SpsSts
        0x1F00E, # XW+/MPPT / ChgSts -- charger status
        0x1F01B, # BattMon / BattMonSts
        0x1F011, # AGS / AgsSts
        0x1F0BE, # MPPT Data
        0x1F014, # ProdInfoSts
        0x1F810, # HwRevSts
        0x1F80E, # SwVerSts
    }

    def __init__(self,
                  pgn,
                  src,
                  dst,
                  pri):
          
          self.pgn = pgn
          self.src = src
          self.dst = dst
          self.pri = pri

          self.data = None
          self.is_fast_packet = (self.pgn in self.xanbus_fast_packets)
          self.is_ready = (not self.is_fast_packet)
          self.sequence_id = 0
          self.total_length = 0
          self.is_bogus = False

    def append_bytes(self, message):
        if self.is_fast_packet:
            # https://www.csselectronics.com/pages/nmea-2000-n2k-intro-tutorial#fast-packet
            # NMEA2000 fast-packet control byte is a 3-bit sequence counter in
            # the high bits and a 5-bit frame index in the low 5 bits (0..31) --
            # NOT a 4/4 nibble split. The nibble split is indistinguishable for
            # messages of <=16 frames (the frame index's high bit stays 0), which
            # is why it worked for most PGNs. But for PGN 0x1F0BE, whose message
            # exceeds 16 frames, the frame index's bit 4 flips at frame 16 and,
            # under the nibble split, leaks into the sequence id (and can make
            # frame 16 look like a fresh frame-0) -- which is why the sequence
            # check below had to be disabled. The spec-correct 5-bit split fixes
            # both.
            first_byte = int.from_bytes(message.data[:1])
            sequence_id = first_byte >> 5  # top 3 bits
            frame_id = first_byte & 0x1F   # bottom 5 bits (0..31)
            #print(f'{first_byte:b} {first_byte:x} {sequence_id} {frame_id}')

            if frame_id == 0 and self.data == None:
                self.sequence_id = sequence_id
                self.total_length = int.from_bytes(message.data[1:2])
                #print(f"TOTAL LENGTH TO READ: {self.total_length} sequence_id={sequence_id} pgn={self.pgn:x}")
                if self.total_length == 0:
                    self.is_bogus = True
                    return
                self.data = bytearray(message.data[2:])
            else:
                if self.data == None:
                    #print(f"GOT ANOTHER FAST PACKET BUT NOT THE FIRST ONE pgn: {self.pgn:x} - cur: {self.sequence_id}  got: {sequence_id}  -- IGNORING FOR NOW")
                    self.is_bogus = True
                    return

                # Re-enabled: with the correct 5-bit frame index above, the
                # sequence-id no longer flips at frame 16, so this integrity
                # check is safe for every PGN including 1f0be (>16 frames). It
                # was previously disabled precisely because the 4/4 nibble split
                # corrupted the sequence-id past frame 15. This rejects
                # interleaved / partially-missed messages instead of silently
                # concatenating them.
                if self.sequence_id != sequence_id:
                    self.is_bogus = True
                    return

                data_to_append = message.data[1:]
                self.data += data_to_append

                # Message ready to be processed
                if len(self.data) >= self.total_length:
                    self.is_ready = True
        else:
            self.data = message.data
    
    def bytes(self):
        return self.data