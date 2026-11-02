# Battle Enemy Sprites — format & data notes

Documentation for the **Battle enemy graphics** editor (`Edit → Battle enemy graphics…`).

Test with **Final Fantasy Mystic Quest, USA v1.0**, unheadered, CRC32 6b19a2c6, SHA-256 `6151389f33ce2e53db3cd99592440c0020f5f4668f581ce3bd615bc92077f255`.

## ROM layout

* **Pointer table:** file `0x48460` = SNES `$098460` (bank `$09`). **83 entries × 5 bytes**: `[addr_lo, addr_hi, bank, flags, 0x00]`. Entry index == enemy id (matches `monster_stat` at `$02C275`, 83 × 14 bytes, and `monster_name` at `$0CCBA0`, 81 × 16 bytes). Entries **0–80 are real**; **81–82 are junk** (bogus pointers) and are hidden in the editor.
* **Art location:** `file = bank*0x8000 + (addr - 0x8000)`. Art lives in banks `$09–$0B` (file `0x48000`–`~0x5EB6A`). The region ends where a 2-byte pointer table begins near file `0x5EB6A`.
* **Tile format:** **3bpp** (3 bit-planes, 8 colors), **24 bytes** per 8×8 tile, contiguous. `bytes[0..15]` = plane0/plane1 interleaved per row; `bytes[16..23]` = plane2.
* **Decompression (ExpandSecondHalfWithZeros):** each 24-byte ROM tile → 32-byte 4bpp VRAM tile: `vram[0..15] = src[0..15]`; `vram[16..31] = [src16,0, src17,0, …, src23,0]` (plane 3 = 0).
* **Palette:** not stored in the tiles (indices 0–7 only). Each OBJ tile picks a palette via its OAM attribute, so one enemy can use **multiple palettes** (the Dark King). The editor derives a per-tile palette from reference art.
* **Composition:** tiles are **not** row-major; the game places them with per-tile positions and reuses tiles across cells/frames. The editor uses precomputed **placements** to compose each enemy.

## Editing model

* Edits are sparse `battle_graphic` changes keyed by tile **file offset**, span fixed at **24 bytes**. An edit can never change size or shift data (the expansion is fixed 24→32), and `span` rejects out-of-range/table offsets and any byte index ≥ 24, so the pointer table is protected.
* PNG **export/import**: export writes an indexed PNG of the composed frame; import maps each cell's pixels back to tile indices via that cell's palette (round-trip is lossless for correctly-placed enemies).
