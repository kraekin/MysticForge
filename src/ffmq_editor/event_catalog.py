"""Bounded, read-only event inventory and direct incoming references."""
from dataclasses import dataclass,field
from collections import deque
from .events import decode,npc_entry,world_entry,fragments,status
from .event_presentation import readable_rows,Dialogue
from .event_flags import flag_uses

@dataclass(frozen=True)
class Reference:
    kind:str
    label:str
    target:tuple

@dataclass
class EventRecord:
    address:int
    extent:int|None=None
    aliases:set=field(default_factory=set)
    references:set=field(default_factory=set)
    preview:str=''
    dialogues:tuple=()
    flags:tuple=()
    issues:set=field(default_factory=set)

    @property
    def key(self):return self.address,self.extent

    @property
    def search_text(self):
        return ' '.join([f'{self.address:06x}',f'{self.address>>16:02x}:{self.address&65535:04x}',*sorted(self.aliases),self.preview,*(r.label for r in self.references)]).lower()

class EventCatalog:
    def __init__(self,rom,project):
        self.records={};self.notes=[];queue=deque();dictionary=dict(fragments(rom))
        def add(address,alias='',ref=None,extent=None):
            extent=dictionary.get(address) if extent is None else extent
            key=(address,extent)
            if key not in self.records:
                if len(self.records)>=4096:
                    self.notes.append('Event inventory limit reached; some linked targets are not indexed.');return
                self.records[key]=EventRecord(address,extent);queue.append(key)
            record=self.records[key]
            if alias:record.aliases.add(alias)
            if ref:record.references.add(ref)
        for i in range(124):
            address=npc_entry(rom,i)
            if address is not None:add(address,f'NPC ${i:02X}')
        for i in range(80):add(world_entry(rom,i),f'World / cutscene ${i:02X}')
        for i,(address,extent) in enumerate(fragments(rom)):add(address,f'Text fragment ${i:02X}',extent=extent)
        add(0x038686,'Shared chest interaction')
        for area in rom.areas:
            for index,obj in enumerate(project.objects(area.id)):
                kind=(obj[5]>>3)&3
                address=npc_entry(rom,obj[1]) if kind==0 else 0x038686 if kind==2 and obj[1]<251 else None
                if address is not None:
                    add(address,ref=Reference('Object',f'{area.name} · area ${area.id:02X}, object ${index:02X}',(area.id,index)))
        # Ordinary terrain entrances dispatch native transitions, not event IDs.
        # World nodes explicitly store action $08 + a world event reference.
        for area in rom.areas:
            if area.layout_id!=0:continue
            for node in range(0x16,0x38):
                value,action=project.fixed('world_action',node)
                if action==8 and value<80:
                    add(world_entry(rom,value),ref=Reference('Entrance',f'{area.name} · area ${area.id:02X}, world node ${node:02X}',(area.id,node)))
        total=0
        while queue:
            key=queue.popleft();record=self.records[key]
            if total>=250000:
                record.issues.add('Not scanned: total inspection limit');continue
            rows=decode(rom,record.address,limit=min(8192,250000-total),follow_calls=False,extent=record.extent)
            total+=len(rows)
            record.issues.update(status(r) for r in rows if not r.complete)
            presentation=readable_rows(rom,rows)
            record.preview='\n'.join(r.text if isinstance(r,Dialogue) else r.description for r in presentation)
            record.dialogues=tuple(r.text for r in presentation if isinstance(r,Dialogue))
            record.flags=tuple(dict.fromkeys(use for row in rows for use in flag_uses(row)))
            for row in rows:
                for label,target in row.edges:
                    if label=='next':continue
                    extent=row.raw[-1] if label=='bounded' else None
                    if label not in ('call','fragment','bounded') and record.extent is not None and record.address<=target<record.address+record.extent:
                        extent=record.address+record.extent-target
                    add(target,ref=Reference('Event',f'{label.capitalize()} from ${record.address:06X} at ${row.address:06X}',key),extent=extent)
                # Native world-event dispatch is not an ordinary bytecode call.
                words=[row.raw[1:3]] if row.raw[:1]==b'\x2c' else [row.raw[i:i+2] for i in range(1,len(row.raw)-2,2)] if row.raw[:1]==b'\x2a' and row.complete else []
                for word in words:
                    if len(word)==2 and word[1]==8 and word[0]<80:
                        add(world_entry(rom,word[0]),ref=Reference('Event',f'World event ${word[0]:02X} from ${record.address:06X} at ${row.address:06X}',key))
        self.notes=sorted(set(self.notes))
        if total>=250000:self.notes.append('Total decoding limit reached; unscanned entries are marked.')
        # Add stable table names to caller labels after all aliases are known.
        for record in self.records.values():
            references=set()
            for ref in record.references:
                names=sorted(self.records[ref.target].aliases) if ref.kind=='Event' else []
                references.add(Reference(ref.kind,(', '.join(names)+' · ' if names else '')+ref.label,ref.target))
            record.references=references
