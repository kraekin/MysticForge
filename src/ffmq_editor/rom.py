"""Exact-base-ROM structures, derived from banks 01, 06, 07 and 0B.

See research/ASSEMBLY_FINDINGS.md. No external disassembly is needed at runtime.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib

BASE_SHA256 = "6151389f33ce2e53db3cd99592440c0020f5f4668f581ce3bd615bc92077f255"
LAYOUT_NAMES = (
    "Overworld", "Unknown layout 01", "Foresta", "Aquaria", "Windia", "Fireburg",
    "Hill of Destiny", "Level / Alive Forest", "Wintry Cave", "Mine exterior",
    "Volcano summit", "Volcano base", "Rope Bridge", "Giant Tree A", "Giant Tree B",
    "Giant Tree exterior", "Mount Gale", "Mac's ship deck", "Mac's ship interior",
    "Bone Dungeon", "Ice Pyramid A", "Ice Pyramid B", "Lava Dome exterior",
    "Lava Dome interior A", "Lava Dome interior B", "Pazuzu's Tower A", "Pazuzu's Tower B",
    "Spencer's Cave", "Ship Dock", "Fall Basin", "House interiors", "Caves",
    "Foresta interiors", "Focus Tower base", "Focus Tower", "Doom Castle ice",
    "Doom Castle lava", "Doom Castle sky", "Doom Castle hero", "Dark King's room",
    "Background A", "Background B", "Background C", "Background D",
)

class FormatError(ValueError):
    pass

def pc(address: int, *, expanded=False) -> int:
    bank, offset = address >> 16, address & 0xFFFF
    if not 0 <= bank <= (31 if expanded else 15) or offset < 0x8000:
        raise FormatError(f"Address ${address:06X} is outside the supported ROM mapping")
    return bank * 0x8000 + offset - 0x8000

def read(data: bytes, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise FormatError(f"Read outside ROM at file ${offset:06X}, length {size}")
    return data[offset:offset+size]

def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(read(data, offset, 2), "little")

@dataclass(frozen=True)
class Decoded:
    cells: bytes
    start: int
    end: int
    literal_start: int

def decode_map(data: bytes, start: int, limit: int = 0x4000) -> Decoded:
    """Bank 0B:8669 split-stream decoder, with checked bank-local reads."""
    bank_end = (start // 0x8000 + 1) * 0x8000
    literal = start + 2 + u16(data, start)
    literal_start = literal
    cursor = start + 2
    out = bytearray()
    if not cursor < literal <= min(bank_end, len(data)):
        raise FormatError("Invalid literal-stream offset")
    while cursor < literal_start:
        command = data[cursor]
        cursor += 1
        if not command:
            return Decoded(bytes(out), start, literal, literal_start)
        count, run = command & 15, command >> 4
        if literal + count > min(bank_end, len(data)):
            raise FormatError("Literal stream crosses a ROM bank")
        out.extend(data[literal:literal+count])
        literal += count
        if run:
            if cursor >= literal_start:
                raise FormatError("Missing back-reference distance")
            distance = data[cursor] + 1
            cursor += 1
            if distance > len(out):
                raise FormatError("Back-reference precedes output")
            for _ in range(run + 2):
                out.append(out[-distance])
        if len(out) > limit:
            raise FormatError("Decompressed layout exceeds limit")
    raise FormatError("Map command stream has no terminator")

def encode_map(cells: bytes) -> bytes:
    """Minimum-byte command sequence for this codec using dynamic programming.

    A command may combine up to 15 literal bytes and a 3..17-byte back-reference.
    The objective includes BOTH streams. All distances are limited to 256 bytes.
    """
    size=len(cells)
    if size>0x4000:raise FormatError("Layout is too large")
    matches=[(0,0)]*size
    positions={}
    for pos in range(size):
        triple=cells[pos:pos+3]
        candidates=positions.setdefault(triple,[])
        best_length,best_distance=0,0
        for source in reversed(candidates):
            distance=pos-source
            if distance>256:break
            length=0
            while length<17 and pos+length<size and cells[pos+length]==cells[pos+length-distance]:
                length+=1
            if length>best_length:
                best_length,best_distance=length,distance
                if length==17:break
        candidates.append(pos)
        matches[pos]=(best_length,best_distance)
    costs=[10**9]*(size+1);costs[size]=1 # terminator
    choice=[None]*size;refs=[None]*size
    for pos in range(size-1,-1,-1):
        length,distance=matches[pos]
        if length>=3:
            run=min(range(3,length+1),key=lambda n:costs[pos+n])
            refs[pos]=(costs[pos+run]+2,run,distance)
        for literal in range(min(15,size-pos)+1):
            following=pos+literal
            if literal and literal+1+costs[following]<costs[pos]:
                costs[pos]=literal+1+costs[following];choice[pos]=(literal,0,0)
            if following<size and refs[following] is not None:
                ref_cost,run,distance=refs[following]
                if literal+ref_cost<costs[pos]:
                    costs[pos]=literal+ref_cost;choice[pos]=(literal,run,distance)
    commands,literals=bytearray(),bytearray()
    pos=0
    while pos<size:
        count,run,distance=choice[pos]
        commands.append(count | (((run-2)<<4) if run else 0))
        literals.extend(cells[pos:pos+count])
        if run:commands.append(distance-1)
        pos+=count+run
    commands.append(0)
    return len(commands).to_bytes(2, "little") + commands + literals

def decode_rle(data: bytes, start: int) -> bytes:
    """Bank 0B:86EA: length counts encoded payload bytes."""
    length = u16(data, start)
    payload = read(data, start+2, length)
    if start+2+length > (start // 0x8000+1)*0x8000:
        raise FormatError("RLE payload crosses bank")
    out, i = bytearray(), 0
    while i < len(payload):
        value = payload[i]
        i += 1
        if value & 0x80:
            if i == len(payload):
                raise FormatError("Truncated RLE token")
            out.extend([value & 0x7F] * (payload[i]+3))
            i += 1
        else:
            out.append(value)
        if len(out) > 0x4000:
            raise FormatError("RLE output exceeds limit")
    return bytes(out)

@dataclass(frozen=True)
class Attributes:
    raw: bytes
    width: int
    height: int

    @property
    def tileset(self):
        return self.raw[0] & 15

    @property
    def palette(self):
        return self.raw[1]

@dataclass(frozen=True)
class Area:
    id: int
    offset: int
    header: bytes
    objects: tuple[bytes, ...]
    title: str | None = None
    attribute_override: int | None = None

    @property
    def layout_id(self):
        return self.header[0] & 63

    @property
    def attributes_id(self):
        return self.header[1] if self.attribute_override is None else self.attribute_override

    @property
    def name(self):
        return self.title or LAYOUT_NAMES[self.layout_id]

@dataclass(frozen=True)
class MapChange:
    id: int
    offset: int
    x: int
    y: int
    width: int
    height: int
    cells: bytes

@dataclass(frozen=True)
class Action:
    flag: int
    value: int
    opcode: int

class Rom:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.data = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        if self.sha256 != BASE_SHA256:
            raise FormatError("Unsupported base ROM. Select the original unheadered ROM used by this project.")
        self.layouts = tuple(decode_map(self.data, pc(int.from_bytes(read(self.data, pc(0x0B8735)+i*3, 3), "little"))) for i in range(44))
        attrs = []
        for i in range(44):
            raw = read(self.data, pc(0x0B8CD9)+i*10, 10)
            width, height = read(self.data, pc(0x0B8540)+(raw[0] >> 4)*2, 2)
            attrs.append(Attributes(raw, width, height))
        self.attributes = tuple(attrs)
        from .world import inventory
        self.routes=inventory(self.data)
        self.route_sizes={r.offset:r.size for r in self.routes}
        areas = []
        for i in range(108):
            offset = pc(0x07B013) + u16(self.data, pc(0x07AF3B)+i*2)
            header = read(self.data, offset, 8)
            objects, cursor = [], offset+8
            while read(self.data, cursor, 1)[0] != 0xFF:
                objects.append(read(self.data, cursor, 7))
                cursor += 7
                if len(objects) > 256:
                    raise FormatError("Unterminated object list")
            areas.append(Area(i, offset, header, tuple(objects)))
        self.areas = tuple(areas)
        self.coordinate_offsets=set()
        start=pc(0x05F9F8)
        for p in range(start,pc(0x05FFFF)-1,3):
            if self.data[p+1]&128:break
            self.coordinate_offsets.add(p)
        self.object_references={}
        self.object_capacities={a.offset:len(a.objects) for a in self.areas}
        self.structural_object_sets={a.offset for a in self.areas if not any(
            b.offset!=a.offset and max(a.offset,b.offset)<min(a.offset+9+len(a.objects)*7,b.offset+9+len(b.objects)*7)
            for b in self.areas)}
        for area in self.areas:
            for index in range(len(area.objects)):
                offset=area.offset+8+index*7
                self.object_references.setdefault(offset,[]).append((area.id,index))
        changes = []
        for i in range(106):
            offset = pc(0x06BA0E)+u16(self.data, pc(0x06B93A)+2*i)
            x, y, size = read(self.data, offset, 3)
            w, h = size >> 4, size & 15
            changes.append(MapChange(i, offset, x, y, w, h, read(self.data, offset+3, w*h)))
        self.changes = tuple(changes)
        self.area_actions = tuple(self._actions(i) for i in range(108))
        self.initial_flags = frozenset(i for i in range(256) if self.data[0x653A4+i//8] & (0x80 >> (i&7)))

    def _actions(self, area_id):
        table_id = self.data[pc(0x06BE77)+area_id]
        if table_id & 0x80:
            return ()
        cursor = pc(0x06BF15)+u16(self.data, pc(0x06BEE3)+2*table_id)
        actions = []
        while read(self.data, cursor, 1)[0] != 0xFF:
            actions.append(Action(*read(self.data, cursor, 3)))
            cursor += 3
            if len(actions) > 100:
                raise FormatError("Unterminated map action list")
        return tuple(actions)

    def remaps(self, index):
        if not 0 <= index < 11:
            raise FormatError("Metatile replacement index outside table")
        cursor = pc(0x06BD78)+u16(self.data, pc(0x06BD62)+2*index)
        result = []
        while self.data[cursor] != 0xFF:
            dest, source = read(self.data, cursor, 2)
            if max(dest, source) >= 128:
                raise FormatError("Metatile replacement outside set")
            result.append((dest, source))
            cursor += 2
        return tuple(result)

    def palette_offset(self, palette):
        if not 0 <= palette <= 0x19:
            raise FormatError("Palette outside supported table")
        return pc(0x07D984) if palette == 0x19 else pc(0x058000)+palette*128

    def shared_areas(self, layout_id):
        return tuple(a.id for a in self.areas if a.layout_id == layout_id)
