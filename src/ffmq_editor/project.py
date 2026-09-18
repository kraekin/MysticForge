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
        self.base_rom=getattr(rom,"base_rom",rom)
        self.newmaps={}
        self.sprite_sets={}
        self.event_edits={}
        self.private_dialogues={}
        self.setup_labels={}
        self.edits: dict[tuple[str, int, int], int] = {}
        self.path: Path | None = None
        self.flags = set(rom.initial_flags)
        self.area_id = 0
        self.expanded = False
        self.layout_copies = {}
        self.layout_bindings = {}
        from .expanded_content import empty
        self.content=empty()
        self.world={"routes":{},"nodes":{}}
        self.landmarks=None

    def tileset(self,area_id):
        return next((i for i,c in self.content['sets'].items() if c['area']==area_id),self.rom.attributes[self.rom.areas[area_id].attributes_id].tileset)

    def object_capacity(self,area_id):
        area=self.rom.areas[area_id]
        return max(len(area.objects),16) if self.expanded and area.layout_id!=0 else len(area.objects)

    def object_key(self,area_id,index,byte):
        area=self.rom.areas[area_id]
        return ('object',area.offset+8+index*7,byte) if index<len(area.objects) else ('extra_object',area.offset,index*7+byte)

    @property
    def coordinate_offsets(self):
        from .expanded_content import coordinate_id
        return self.rom.coordinate_offsets|{coordinate_id(i) for i in self.content['entrances']}

    def layout_id(self, area_id):
        return self.layout_bindings.get(area_id,self.rom.areas[area_id].layout_id)

    def shared_areas(self, layout_id):
        return tuple(a.id for a in self.rom.areas if self.layout_id(a.id)==layout_id)

    def layout_original(self, resource):
        if resource in self.layout_copies:return self.layout_copies[resource]['cells']
        if type(resource) is int and 0<=resource<len(self.rom.layouts):return self.rom.layouts[resource].cells
        raise FormatError('Unknown layout resource')

    def validate_expansion(self):
        from .event_editing import validate as validate_events
        validate_events(self)
        from .private_dialogue import validate as validate_dialogues
        validate_dialogues(self)
        from .new_maps import sync_catalog,validate as validate_maps
        sync_catalog(self);validate_maps(self)
        from .map_setups import validate as validate_setups
        validate_setups(self)
        from .sprite_sets import validate as validate_sprites
        validate_sprites(self)
        from .expanded_content import validate
        validate(self)
        from .world_expansion import validate_structure
        validate_structure(self)
        from .landmarks import validate as validate_landmarks
        validate_landmarks(self)
        if type(self.expanded) is not bool:raise FormatError('Invalid expansion setting')
        if (self.layout_copies or self.layout_bindings) and not self.expanded:raise FormatError('Independent terrain requires expanded ROM export')
        for resource,copy in self.layout_copies.items():
            if type(resource) is not int or not 44<=resource<64 or not isinstance(copy,dict) or set(copy)!= {'source','cells'}:
                raise FormatError('Invalid independent layout')
            source=copy['source']
            if type(source) is not int or not 0<=source<44 or not isinstance(copy['cells'],bytes) or len(copy['cells'])!=len(self.rom.layouts[source].cells):
                raise FormatError('Invalid independent layout source or geometry')
        for area_id,resource in self.layout_bindings.items():
            if type(area_id) is not int or not 0<=area_id<len(self.rom.areas) or type(resource) is not int or resource not in self.layout_copies:
                raise FormatError('Invalid terrain binding')
            area=self.rom.areas[area_id]
            if area.id<108 and self.layout_copies[resource]['source']!=area.layout_id:raise FormatError('Terrain copy belongs to a different original layout')
            if any(self.layout_id(a.id)!=resource for a in self.rom.areas if a.offset==area.offset):
                raise FormatError('Configurations sharing an area record must retain the same terrain binding')
        if set(self.layout_bindings.values())!=set(self.layout_copies):raise FormatError('Unreferenced independent layout')

    def copy_terrain(self, area_id):
        self.validate_expansion()
        if type(area_id) is not int or not 0<=area_id<len(self.rom.areas):raise FormatError('Invalid terrain configuration')
        if not self.expanded:raise FormatError('Enable 1 MiB expanded export first')
        area=self.rom.areas[area_id]
        if area_id in self.layout_bindings:raise FormatError('This configuration already has independent terrain')
        available=next((i for i in range(44,64) if i not in self.layout_copies),None)
        if available is None:raise FormatError('All 20 independent layout slots are in use')
        members=[a.id for a in self.rom.areas if a.offset==area.offset]
        self.layout_copies[available]={'source':area.layout_id,'cells':self.resource('layout',self.layout_id(area_id))}
        for member in members:self.layout_bindings[member]=available
        self.validate_expansion()
        return available

    def original(self, key):
        kind, resource, index = key
        if kind in ("world_node","world_gate","world_action") and resource in self.world["nodes"]:
            data=self.world["nodes"][resource][{"world_node":"position","world_gate":"gates","world_action":"action"}[kind]]
            if not 0<=index<len(data):raise FormatError("Expanded node field out of bounds")
            return data[index]
        if type(resource) is not int or type(index) is not int or resource < 0 or index < 0:
            raise FormatError("Invalid edit coordinate")
        if kind=="bugfix" and resource==0 and index==0:return 0
        from .expanded_content import KINDS,entrance_index
        if kind in KINDS and resource in self.content['sets']:
            field,size=KINDS[kind];data=self.content['sets'][resource][field]
            if index>=size:raise FormatError('Private metatile edit exceeds its data')
            return data[index]
        if kind=='extra_object' and resource in self.rom.object_capacities:
            area=next(a for a in self.rom.areas if a.offset==resource)
            if len(area.objects)*7<=index<max(16,len(area.objects))*7:return 0
            raise FormatError('Extra object exceeds supported slots')
        base=0x200000 if kind=='coordinate' else 0x210000 if kind=='destination' else -1
        extra=entrance_index(resource,base) if base>=0 else None
        if kind=='destination':
            from .new_maps import destination
            new=destination(self,resource)
            if new is not None:
                if index>=3:raise FormatError('Destination edit exceeds record')
                return new[index]
        if extra in self.content['entrances']:
            c=self.content['entrances'][extra];data=bytes((c['x'],c['y'],217+extra)) if kind=='coordinate' else c['target']
            if index>=3:raise FormatError('Entrance edit exceeds record')
            return data[index]
        if kind == "layout":
            data = self.layout_original(resource)
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
        elif kind in ("terrain_graphic","metatile_graphics","metatile_attributes","properties","destination","world_node","world_action","world_gate","treasure","encounter","formation","monster_stat","monster_level","monster_attacks","monster_name","attack","attack_name","weapon","armor","character","battlefield"):
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
        if ((key[0]=="object" and key[2]==0) or (key[0]=='extra_object' and key[2]%7==0)) and value==255:
            raise FormatError("FF is the object-list terminator, not a visibility flag")
        if key[0]=="object_count" and value>self.object_capacity(next(a.id for a in self.rom.areas if a.offset==key[1])):
            raise FormatError("Object list exceeds its verified capacity; relocation is required")
        if value == original:
            self.edits.pop(key, None)
        else:
            self.edits[key] = value

    def resource(self, kind, resource):
        original = self.layout_original(resource) if kind == "layout" else self.rom.changes[resource].cells
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
        return tuple(bytes(self.get(self.object_key(area_id,i,b)) for b in range(7))
                     for i in range(count))

    def fixed(self,kind,resource):
        from .expanded_content import KINDS,entrance_index
        from .new_maps import destination
        if kind=="destination" and destination(self,resource) is not None:return bytes(self.get((kind,resource,i)) for i in range(3))
        size=({"world_node":2,"world_gate":4,"world_action":2}[kind] if kind in ("world_node","world_gate","world_action") and resource in self.world["nodes"] else None)
        size=size if size is not None else KINDS[kind][1] if kind in KINDS and resource in self.content['sets'] else 3 if kind=="coordinate" or (kind=='destination' and entrance_index(resource,0x210000) in self.content['entrances']) else self.rom.route_sizes[resource] if kind=="world_route" else span(kind,resource)[1]
        return bytes(self.get((kind,resource,i)) for i in range(size))

    def state(self, area_id: int, flags=None) -> StateView:
        flags = self.flags if flags is None else flags
        area = self.rom.areas[area_id]
        attrs = self.rom.attributes[area.attributes_id]
        cells = bytearray(self.resource("layout", self.layout_id(area_id)))
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
        self.validate_expansion()
        from .expanded_content import encode
        from .world_expansion import encode as encode_world
        return {"format": "ffmq-map-project", "version": 13,
                "private_dialogues":[[a,r] for a,r in sorted(self.private_dialogues.items())],
                "setup_labels":[[a,r] for a,r in sorted(self.setup_labels.items())],
                "event_edits":[[a,r] for a,r in sorted(self.event_edits.items())], "base_sha256": BASE_SHA256,
                "content":encode(self),
                "world":encode_world(self),
                "sprite_sets":[[i,{"labels":c["labels"],"base":c["base"],"data":c["data"].hex(),"presets":[o.hex() for o in c["presets"]]}] for i,c in sorted(self.sprite_sets.items())],
                "newmaps":[[i,c] for i,c in sorted(self.newmaps.items())],
                "landmarks":None if self.landmarks is None else [r.hex() for r in self.landmarks],
                "expansion": {"enabled":self.expanded,"layouts":[{'id':i,'source':c['source'],'cells':c['cells'].hex()} for i,c in sorted(self.layout_copies.items())],"bindings":[list(x) for x in sorted(self.layout_bindings.items())]},
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
        if document.get("format") != "ffmq-map-project" or document.get("version") not in (1,2,3,4,5,6,7,8,9,10,11,12,13) or document.get("base_sha256") != BASE_SHA256:
            raise FormatError("Unsupported project or base ROM")
        project = cls(rom)
        try:
            for a,r in document.get("private_dialogues",[]):
                if type(a) is not int or a in project.private_dialogues:raise ValueError("Duplicate or invalid dialogue ID")
                project.private_dialogues[a]=r
        except (TypeError,ValueError) as e:raise FormatError("Invalid independent dialogue") from e
        try:
            for a,r in document.get("setup_labels",[]):
                if a in project.setup_labels:raise ValueError("Duplicate setup label")
                project.setup_labels[a]=r
        except (TypeError,ValueError) as e:raise FormatError("Invalid map setup labels") from e
        if document.get("version") in (9,10,11,12,13):
            try:
                for a,r in document.get("event_edits",[]):
                    if a in project.event_edits:raise ValueError("Duplicate event edit")
                    project.event_edits[a]=r
            except (TypeError,ValueError) as e:raise FormatError("Invalid event edits") from e
        if document.get("version") in (8,9,10,11,12,13):
            try:
                for i,c in document.get("sprite_sets",[]):
                    if i in project.sprite_sets:raise ValueError('Duplicate sprite set')
                    project.sprite_sets[i]={"labels":c.get("labels",[f"Imported preset {n+1}" for n in range(len(c["presets"]))]),"base":c["base"],"data":bytes.fromhex(c["data"]),"presets":[bytes.fromhex(o) for o in c["presets"]]}
            except (KeyError,TypeError,ValueError) as e:raise FormatError('Invalid private sprite sets') from e
        if document.get("version") in (7,8,9,10,11,12,13):
            for i,c in document.get("newmaps",[]):
                if i in project.newmaps:raise FormatError("Duplicate map ID")
                project.newmaps[i]=c
        if document.get("version") in (6,7,8,9,10,11,12,13) and document.get("landmarks") is not None:
            try:project.landmarks=[bytes.fromhex(r) for r in document["landmarks"]]
            except (TypeError,ValueError) as e:raise FormatError("Invalid landmark data") from e
        if document.get("version") in (5,6,7,8,9,10,11,12,13):
            from .world_expansion import decode
            project.world=decode(document["world"])
        if document.get('version') in (4,5,6,7,8,9,10,11,12,13):
            from .expanded_content import decode
            try:project.content=decode(document['content'])
            except (KeyError,TypeError,ValueError) as error:raise FormatError('Invalid expanded content: '+str(error)) from error
        if document.get('version') in (3,4,5,6,7,8,9,10,11,12,13):
            try:
                expansion=document['expansion'];project.expanded=expansion['enabled']
                for copy in expansion['layouts']:
                    resource=copy['id']
                    if resource in project.layout_copies:raise ValueError('Duplicate layout')
                    project.layout_copies[resource]={'source':copy['source'],'cells':bytes.fromhex(copy['cells'])}
                for area_id,resource in expansion['bindings']:
                    if area_id in project.layout_bindings:raise ValueError('Duplicate binding')
                    project.layout_bindings[area_id]=resource
                project.validate_expansion()
            except (KeyError,TypeError,ValueError) as error:raise FormatError('Invalid expansion data: '+str(error)) from error
        seen = set()
        for item in document.get("edits", []):
            if not isinstance(item, list) or len(item) != 4:
                raise FormatError("Invalid edit record")
            key = tuple(item[:3])
            if key in seen:
                raise FormatError("Duplicate edit record")
            seen.add(key)
            project.set(key, item[3])
        project.validate_expansion()
        preview = document.get("preview", {})
        area = preview.get("area", 0)
        flags = preview.get("flags", list(rom.initial_flags))
        if type(area) is not int or not 0 <= area < len(project.rom.areas) or not isinstance(flags, list) or any(type(i) is not int or not 0 <= i < 256 for i in flags):
            raise FormatError("Invalid preview state")
        project.area_id, project.flags, project.path = area, set(flags), path.resolve()
        return project

    def build(self):
        from .layout_storage import plan_layouts,POINTERS
        self.validate_expansion()
        plan=plan_layouts(self) if self.expanded or any(k=='layout' for k,_,_ in self.edits) else None
        output = bytearray(self.rom.data)
        if self.expanded:output.extend(b'\xff'*(0x100000-len(output)))
        writes = {}
        expanded_spans = []
        report = []
        def write(offset, data, description):
            if offset<0 or offset+len(data)>len(output):raise FormatError('Export write is outside allocated ROM')
            # Expanded resources have one owner, even when overlapping bytes
            # happen to be equal. Check the final writes as well as the planner.
            if data and offset+len(data)>0x80000:
                start=max(offset,0x80000);end=offset+len(data)
                for prior_start,prior_end,prior_name in expanded_spans:
                    if start<prior_end and prior_start<end:
                        raise FormatError(f'Expanded storage overlap: {description} and {prior_name} at file ${max(start,prior_start):06X}.')
                expanded_spans.append((start,end,description))
            for i, value in enumerate(data):
                address = offset+i
                if address in writes and writes[address] != value:
                    raise FormatError("Conflicting resource writes")
                writes[address] = value
            output[offset:offset+len(data)] = data
            report.append({"resource": description, "offset": offset, "bytes": len(data)})
        changed = {(kind, resource) for kind, resource, _ in self.edits}
        from .expanded_content import KINDS,active,entrance_index
        content_active=active(self)
        if plan is not None:
            for offset,data,description in plan.writes:write(offset,data,description)
        if self.expanded:
            write(0x7fd7,b'\x0a','ROM size: 1 MiB')
            for area_id,resource in self.layout_bindings.items():
                area=self.rom.areas[area_id]
                if area.id>=108:continue
                write(area.offset,bytes(((area.header[0]&0xc0)|resource,)),f'area {area_id:02X} terrain binding')
        for kind, resource in sorted(changed):
            if kind in ('world_node','world_gate','world_action') and resource in self.world['nodes']:continue
            if kind=='extra_object' or (kind in KINDS and resource in self.content['sets']) or (kind in ('coordinate','destination') and resource>=0x200000):continue
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
            elif kind in ("terrain_graphic","metatile_graphics","metatile_attributes","properties","destination","world_node","world_action","coordinate","world_route","world_gate","treasure","encounter","formation","monster_stat","monster_level","monster_attacks","monster_name","attack","attack_name","weapon","armor","character","battlefield"):
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
                if count>self.rom.object_capacities[resource]:continue
                # Inactive slots stay byte-identical except the one terminator.
                # A deleted slot can still have saved edits; the terminator wins.
                offset=resource+8+count*7
                writes.pop(offset,None)
                write(offset,b"\xff",f"object count {resource:06X}")
        if plan is not None:
            # Verify every pointer and layout, including untouched neighbors and
            # secondary-only layouts. Never assume old offsets after relocation.
            from .rom import pc
            for resource in plan.pointers:
                pointer=int.from_bytes(output[plan.table+3*resource:plan.table+3*resource+3],'little')
                if pc(pointer,expanded=self.expanded)!=plan.pointers[resource] or decode_map(output,pc(pointer,expanded=self.expanded)).cells!=self.resource('layout',resource):
                    raise FormatError(f'Export verification failed for layout ${resource:02X}')
            for area in self.rom.areas:
                expected=(area.header[0]&0xc0)|self.layout_id(area.id)
                if area.id<108 and output[area.offset]!=expected:raise FormatError('Exported area terrain binding mismatch')
        if self.world["routes"] or self.world["nodes"]:
            from .world_expansion import verify_output
            verify_output(self,output)
        from .new_maps import writes as new_map_writes
        for offset,data,label in new_map_writes(self):write(offset,data,label)
        from .sprite_sets import writes as sprite_writes
        for offset,data,label in sprite_writes(self):write(offset,data,label)
        from .landmarks import writes as landmark_writes
        for offset,data,label in landmark_writes(self):write(offset,data,label)
        from .event_editing import writes as event_writes
        for offset,data,label in event_writes(self):write(offset,data,label)
        from .private_dialogue import writes as dialogue_writes
        for offset,data,label in dialogue_writes(self):write(offset,data,label)
        if self.edits or self.event_edits or self.expanded or self.landmarks is not None:
            # Both supported sizes are powers of two; checksum bytes sum to 510.
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

    def export_patch(self,path:Path,kind='bps'):
        from .patches import verified_patch
        from . import __version__
        path=Path(path).resolve()
        if kind=='ips' and self.expanded:raise FormatError('Expanded ROM projects require BPS patches; IPS export currently supports original-size ROMs only')
        if kind not in ('bps','ips') or path.suffix.lower()!='.'+kind:
            raise FormatError('Patch filename must end with the selected .bps or .ips extension')
        protected=[self.rom.path]+([self.path] if self.path else [])
        if any(path==p.resolve() or (path.exists() and p.exists() and path.samefile(p)) for p in protected):
            raise FormatError('Choose a separate patch output file')
        output,report=self.build()
        metadata=json.dumps({'tool':'MysticForge','version':__version__,'source':'Final Fantasy - Mystic Quest (USA), unheadered v1.0','source_sha256':BASE_SHA256},sort_keys=True,separators=(',',':')).encode('utf-8')
        patch=verified_patch(self.rom.data,output,kind,metadata)
        atomic_write(path,patch)
        return {'format':kind,'patch_bytes':len(patch),'rom_bytes':len(output),'writes':len(report),'verified':True}
