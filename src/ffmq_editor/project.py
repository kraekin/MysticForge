"""Sparse edits, state evaluation, atomic projects and bounded ROM export."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import tempfile

from .rom import Rom, FormatError, BASE_SHA256, encode_map, decode_map
from .resources import span

def atomic_write(path: Path, data: bytes):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name+".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

@dataclass(frozen=True)
class StateView:
    cells: bytes
    palette: int
    applied: tuple
    remaps: tuple
    warnings: tuple[str, ...]
    flags: frozenset[int]

class Project:
    def __init__(self, rom: Rom):
        self.rom = rom
        self.edits: dict[tuple[str, int, int], int] = {}
        self.path: Path | None = None
        self.flags = set(rom.initial_flags)
        self.area_id = 0

    def original(self, key):
        kind, resource, index = key
        if type(resource) is not int or type(index) is not int or resource < 0 or index < 0:
            raise FormatError("Invalid edit coordinate")
        if kind=="bugfix" and resource==0 and index==0:return 0
        if kind == "layout" and resource < len(self.rom.layouts):
            data = self.rom.layouts[resource].cells
        elif kind == "change" and resource < len(self.rom.changes):
            data = self.rom.changes[resource].cells
        elif kind == "palette" and resource <= 0x19 and index < 64:
            p = self.rom.palette_offset(resource)+index*2
            return int.from_bytes(self.rom.data[p:p+2], "little")
        elif kind == "object" and resource in self.rom.object_references:
            data=self.rom.data[resource:resource+7]
        elif kind=="object_count" and resource in self.rom.structural_object_sets and index==0:
            return self.rom.object_capacities[resource]
        elif kind=="coordinate" and resource in self.rom.coordinate_offsets:
            data=self.rom.data[resource:resource+3]
        elif kind=="world_route" and resource in self.rom.route_sizes:
            data=self.rom.data[resource:resource+self.rom.route_sizes[resource]]
        elif kind in ("metatile_graphics","metatile_attributes","properties","destination","world_node","world_action","world_gate","treasure","encounter","formation","monster_stat","monster_level","monster_attacks","monster_name","attack","attack_name","weapon","armor","character","battlefield"):
            offset,size=span(kind,resource);data=self.rom.data[offset:offset+size]
        else:
            raise FormatError("Unknown edit resource")
        if index >= len(data):
            raise FormatError("Edit exceeds resource bounds")
        return data[index]

    def get(self, key):
        return self.edits.get(key, self.original(key))

    def set(self, key, value):
        original = self.original(key)
        maximum = 1 if key[0]=="bugfix" else (0x7FFF if key[0] == "palette" else 255)
        if type(value) is not int or not 0 <= value <= maximum:
            raise FormatError("Edit value is not representable")
        if key[0]=="object" and key[2]==0 and value==255:
            raise FormatError("FF is the object-list terminator, not a visibility flag")
        if key[0]=="object_count" and value>self.rom.object_capacities[key[1]]:
            raise FormatError("Object list exceeds its verified capacity; relocation is required")
        if value == original:
            self.edits.pop(key, None)
        else:
            self.edits[key] = value

    def resource(self, kind, resource):
        original = self.rom.layouts[resource].cells if kind == "layout" else self.rom.changes[resource].cells
        data = bytearray(original)
        for (k, r, index), value in self.edits.items():
            if (k, r) == (kind, resource):
                data[index] = value
        return bytes(data)

    def palette(self, resource):
        return tuple(self.get(("palette", resource, index)) for index in range(64))

    def objects(self, area_id):
        area=self.rom.areas[area_id]
        count=self.get(("object_count",area.offset,0)) if area.offset in self.rom.structural_object_sets else len(area.objects)
        return tuple(bytes(self.get(("object",area.offset+8+i*7,b)) for b in range(7))
                     for i in range(count))

    def fixed(self,kind,resource):
        size=3 if kind=="coordinate" else self.rom.route_sizes[resource] if kind=="world_route" else span(kind,resource)[1]
        return bytes(self.get((kind,resource,i)) for i in range(size))

    def state(self, area_id: int, flags=None) -> StateView:
        flags = self.flags if flags is None else flags
        area = self.rom.areas[area_id]
        attrs = self.rom.attributes[area.attributes_id]
        cells = bytearray(self.resource("layout", area.layout_id))
        palette, applied, remaps, warnings = attrs.palette, [], [], []
        for action in self.rom.area_actions[area_id]:
            if action.flag not in flags:
                continue
            applied.append(action)
            if action.opcode == 0x24:
                palette = action.value
            elif action.opcode == 0x22:
                change = self.rom.changes[action.value]
                data = self.resource("change", change.id)
                for y in range(change.height):
                    for x in range(change.width):
                        destination = (change.y+y)*attrs.width+change.x+x
                        if change.x+x >= attrs.width or change.y+y >= attrs.height:
                            warnings.append(f"Change ${change.id:02X} extends outside this area's geometry")
                            continue
                        cells[destination] = data[y*change.width+x]
            elif action.opcode == 0x23:
                remaps.extend(self.rom.remaps(action.value))
            else:
                warnings.append(f"Action ${action.opcode:02X} (${action.value:02X}) is listed but not visually simulated")
        return StateView(bytes(cells), palette, tuple(applied), tuple(remaps), tuple(dict.fromkeys(warnings)),frozenset(flags))

    def set_preset(self, name: str):
        # Crystal restoration: 01/02/03 and Wind flag 05. Flag 04 is a separate
        # world event (see the Fireburg/Spencer notes), not Wind restoration.
        # This is a visual preset, not a complete endgame save.
        flags = set(self.rom.initial_flags)
        flags.difference_update((1, 2, 3, 5))
        flags.update({"Initial": (), "Earth restored": (1,), "Water restored": (1,2),
                      "Fire restored": (1,2,3), "All restored": (1,2,3,5)}[name])
        self.flags = flags

    def document(self):
        return {"format": "ffmq-map-project", "version": 2, "base_sha256": BASE_SHA256,
                "edits": [[*key, value] for key, value in sorted(self.edits.items())],
                "preview": {"area": self.area_id, "flags": sorted(self.flags)}}

    def save(self, path: Path, autosave=False):
        path = Path(path).resolve()
        if path == self.rom.path:
            raise FormatError("The base ROM cannot be overwritten")
        atomic_write(path, (json.dumps(self.document(), indent=2)+"\n").encode())
        if not autosave:
            self.path = path

    @classmethod
    def load(cls, rom, path):
        path = Path(path)
        if path.stat().st_size > 16*1024*1024:
            raise FormatError("Project file is too large")
        document = json.loads(path.read_text())
        if document.get("format") != "ffmq-map-project" or document.get("version") not in (1,2) or document.get("base_sha256") != BASE_SHA256:
            raise FormatError("Unsupported project or base ROM")
        project = cls(rom)
        seen = set()
        for item in document.get("edits", []):
            if not isinstance(item, list) or len(item) != 4:
                raise FormatError("Invalid edit record")
            key = tuple(item[:3])
            if key in seen:
                raise FormatError("Duplicate edit record")
            seen.add(key)
            project.set(key, item[3])
        preview = document.get("preview", {})
        area = preview.get("area", 0)
        flags = preview.get("flags", list(rom.initial_flags))
        if type(area) is not int or not 0 <= area < 108 or not isinstance(flags, list) or any(type(i) is not int or not 0 <= i < 256 for i in flags):
            raise FormatError("Invalid preview state")
        project.area_id, project.flags, project.path = area, set(flags), path.resolve()
        return project

    def build(self):
        from .layout_storage import plan_layouts,POINTERS
        plan=plan_layouts(self) if any(k=='layout' for k,_,_ in self.edits) else None
        output = bytearray(self.rom.data)
        writes = {}
        report = []
        def write(offset, data, description):
            for i, value in enumerate(data):
                address = offset+i
                if address in writes and writes[address] != value:
                    raise FormatError("Conflicting resource writes")
                writes[address] = value
            output[offset:offset+len(data)] = data
            report.append({"resource": description, "offset": offset, "bytes": len(data)})
        changed = {(kind, resource) for kind, resource, _ in self.edits}
        if plan is not None:
            for offset,data,description in plan.writes:write(offset,data,description)
        for kind, resource in sorted(changed):
            if kind=="bugfix":
                from .rom_fixes import life_patch
                if resource!=0 or self.get((kind,resource,0))!=1:raise FormatError("Unsupported ROM fix")
                offset,raw=life_patch(self.rom);write(offset,raw,"Life spell undead branch fix")
            elif kind == "layout":
                pass # Written using the verified shared-pool allocation above.
            elif kind == "change":
                write(self.rom.changes[resource].offset+3, self.resource(kind, resource), f"map change {resource:02X}")
            elif kind == "object_count":
                pass # Terminators are written after all object bytes below.
            elif kind == "object":
                raw=bytes(self.get((kind,resource,i)) for i in range(7))
                write(resource,raw,f"object record {resource:06X}")
            elif kind in ("metatile_graphics","metatile_attributes","properties","destination","world_node","world_action","coordinate","world_route","world_gate","treasure","encounter","formation","monster_stat","monster_level","monster_attacks","monster_name","attack","attack_name","weapon","armor","character","battlefield"):
                offset=resource if kind in ("coordinate","world_route") else span(kind,resource)[0]
                raw=self.fixed(kind,resource)
                from .database import TABLES,validate_record
                if kind in TABLES:validate_record(self,kind,resource,raw)
                if kind=="treasure" and raw[0] not in (*range(64),0xdd,0xde):raise FormatError("Unsupported vanilla treasure reward")
                if kind=="encounter" and any(v>=234 for v in raw):raise FormatError("Encounter references an invalid formation")
                if kind=="formation" and (all(v==255 for v in raw[:3]) or any(v!=255 and (v&127)>80 for v in raw[:3])):
                    raise FormatError("Formation must contain 1–3 valid enemies")
                if kind=="coordinate" and (raw[0]>=64 or raw[1]>=64):raise FormatError("Invalid transition coordinates")
                if kind=="destination":
                    area,y,x=raw[-3:]
                    if area>=len(self.rom.areas):raise FormatError("Destination area is invalid")
                    attrs=self.rom.attributes[self.rom.areas[area].attributes_id]
                    if y>=attrs.height or (x&63)>=attrs.width:raise FormatError("Destination is outside its map")
                if kind=="world_node" and (raw[0]>=64 or raw[1]>=48):raise FormatError("World node is outside the overworld")
                if kind=="world_action":
                    from .connections import Connections
                    original_action=self.original((kind,resource,1))
                    if raw[1]!=original_action:raise FormatError("Changing overworld action dispatch requires further verification")
                    if raw[1] not in Connections.TABLES or raw[0]>=Connections.TABLES[raw[1]][1]:
                        raise FormatError("Overworld link is not a supported static destination")
                write(offset,raw,f"{kind} {resource:X}")
            else:
                raw = b"".join(v.to_bytes(2,"little") for v in self.palette(resource))
                write(self.rom.palette_offset(resource), raw, f"palette {resource:02X}")
        if any(kind in ("world_route","world_node","world_gate") for kind,_ in changed):
            from .world import validate
            for route in self.rom.routes:validate(self,route,self.fixed("world_route",route.offset))
        for kind,resource in changed:
            if kind=="object_count":
                count=self.get((kind,resource,0))
                # Inactive slots stay byte-identical except the one terminator.
                # A deleted slot can still have saved edits; the terminator wins.
                offset=resource+8+count*7
                writes.pop(offset,None)
                write(offset,b"\xff",f"object count {resource:06X}")
        if plan is not None:
            # Verify every pointer and layout, including untouched neighbors and
            # secondary-only layouts. Never assume old offsets after relocation.
            from .rom import pc
            for resource in range(len(self.rom.layouts)):
                pointer=int.from_bytes(output[POINTERS+3*resource:POINTERS+3*resource+3],'little')
                if pc(pointer)!=plan.pointers[resource] or decode_map(output,pc(pointer)).cells!=self.resource('layout',resource):
                    raise FormatError(f'Export verification failed for layout ${resource:02X}')
        if self.edits:
            # For this fixed 512 KiB image, the four checksum bytes always sum to 510.
            output[0x7FDC:0x7FE0] = bytes((255,255,0,0))
            checksum = sum(output) & 0xFFFF
            output[0x7FDC:0x7FE0] = (checksum ^ 0xFFFF).to_bytes(2,"little")+checksum.to_bytes(2,"little")
            report.append({"resource": "SNES checksum", "offset": 0x7FDC, "bytes": 4})
        return bytes(output), report

    def export(self, path: Path):
        path = Path(path).resolve()
        if path == self.rom.path or (self.path and path == self.path):
            raise FormatError("Choose a separate output file")
        output, report = self.build()
        atomic_write(path, output)
        return report
