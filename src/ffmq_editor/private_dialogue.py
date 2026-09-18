"""Expanded, bank-contained custom NPC interactions; original scripts stay in place."""
from .rom import pc,FormatError
from .layout_storage import cpu_address

START=0xfc000
TABLE=START
HOOK=START+0x300
DATA=START+0x400
END=0x100000
ORIGINAL=bytes.fromhex('e220a9038519c230a5200aaabf36d603851760')

def compile_text(text):
    from .event_editing import atomize,atom_bytes
    if not isinstance(text,str) or not text.strip() or len(text)>8192:
        raise FormatError('Enter between 1 and 8,192 characters of dialogue.')
    # Use only the shared encoder's explicit text atoms, never dictionary calls.
    # Name opcodes select bank $03 explicitly; $05 $18 uses bank-$00 RAM.
    return b''.join(atom_bytes(atom) for atom in atomize(text))+b'\x00'

def runtime_ids(p):
    cached=getattr(p.base_rom,'_private_dialogue_reserved',None)
    if cached is None:
        import re
        from .event_editing import index
        from .event_context import interaction_note
        cached=set()
        for row in index(p).rows.values():
            note=interaction_note(row.raw,None)
            cached.update(int(v,16) for v in re.findall(r'reference (?:to )?\$([0-9A-F]{2})',(note or '')+' '+row.description))
        p.base_rom._private_dialogue_reserved=cached
    return cached

def used_ids(p):
    # Preserve every original ID, even on hidden objects and other dispatch classes.
    used={o[1] for a in p.base_rom.areas for o in a.objects}
    used.update(o[1] for a in p.rom.areas for o in p.objects(a.id))
    used.update(o[1] for s in p.sprite_sets.values() for o in s['presets'])
    return used|runtime_ids(p)|set(p.private_dialogues)

def assign(p,area,index,text):
    return assign_record(p,area,index,{"text":text})

def assign_record(p,area,index,record):
    if not p.expanded:raise FormatError('Custom NPC dialogue requires 1 MiB expanded export.')
    objects=p.objects(area)
    if not 0<=index<len(objects):raise FormatError('Select an NPC first.')
    obj=objects[index]
    if (obj[5]>>3)&3:raise FormatError('Choose an NPC interaction, not a chest or encounter.')
    key=p.object_key(area,index,1)
    shared=[(a.id,i) for a in p.rom.areas for i in range(len(p.objects(a.id))) if p.object_key(a.id,i,1)==key]
    if len(shared)!=1:raise FormatError('This object record is shared by map setups. An independent object-list copy is needed before changing just this NPC.')
    from .custom_events import record_bytes
    record_bytes(p,record,cpu_address(DATA))
    from .custom_events import validate_speaker_maps
    validate_speaker_maps(record,[area])
    current=obj[1]
    owners=[(a.id,i) for a in p.rom.areas for i,o in enumerate(p.objects(a.id)) if (o[5]>>3)&3==0 and o[1]==current]
    if current in p.private_dialogues and owners==[(area,index)]:ident=current
    else:
        ident=next((i for i in range(124,256) if i not in used_ids(p)),None)
        if ident is None:raise FormatError('No unused NPC interaction IDs remain.')
    prospective=dict(p.private_dialogues);prospective[ident]=record
    if sum(len(record_bytes(p,r,cpu_address(DATA))) for r in prospective.values())>END-DATA:raise FormatError('Custom NPC dialogue storage is full.')
    from copy import deepcopy
    p.private_dialogues=deepcopy(prospective);p.set(key,ident)
    return ident

def validate(p):
    records=p.private_dialogues
    if not isinstance(records,dict):raise FormatError('Invalid independent dialogue table.')
    if not records:return
    if not p.expanded:raise FormatError('Custom NPC dialogue needs expanded export.')
    original={o[1] for a in p.base_rom.areas for o in a.objects}|runtime_ids(p)
    for ident,r in records.items():
        if type(ident) is not int or not 124<=ident<256 or ident in original or not isinstance(r,dict):
            raise FormatError('Invalid independent dialogue record or reserved interaction ID.')
        from .custom_events import record_bytes
        record_bytes(p,r,cpu_address(DATA))
        from .custom_events import validate_speaker_maps
        validate_speaker_maps(r,[a.id for a in p.rom.areas if any(o[1]==ident and ((o[5]>>3)&3)==0 for o in p.objects(a.id))])
    if sum(len(record_bytes(p,r,cpu_address(DATA))) for r in records.values())>END-DATA:raise FormatError('Custom NPC dialogue storage is full.')
    if p.base_rom.data[pc(0x009b8a):pc(0x009b9d)]!=ORIGINAL:raise FormatError('NPC dispatcher does not match USA v1.0.')

def plan(p):
    validate(p);cursor=DATA;entries={};writes=[]
    for ident,r in sorted(p.private_dialogues.items()):
        from .custom_events import record_bytes
        raw=record_bytes(p,r,cpu_address(cursor));entries[ident]=cpu_address(cursor)
        writes.append((cursor,raw,f'Custom NPC event ${ident:02X}'));cursor+=len(raw)
    return entries,writes

def writes(p):
    if not p.private_dialogues:return []
    from .expanded_content import Code
    entries,result=plan(p);table=bytearray(256*3)
    for ident,address in entries.items():table[ident*3:ident*3+3]=address.to_bytes(3,'little')
    # Run original pointer setup first. Preserve X=2*ID, return A=pointer,
    # M/X=16, and replace only DP $17..$19 for a nonzero custom bank entry.
    c=Code();c.emit(ORIGINAL[:-1].hex());c.emit('da 8a 18 65 20 aa e2 20')
    c.emit('bf'+cpu_address(TABLE+2).to_bytes(3,'little').hex());c.branch(0xf0,'fallback')
    c.emit('85 19 c2 20 bf'+cpu_address(TABLE).to_bytes(3,'little').hex()+'85 17');c.branch(0x80,'done')
    c.label('fallback');c.emit('c2 20 a5 17');c.label('done');c.emit('fa 6b')
    result.extend([(TABLE,bytes(table),'Independent NPC pointer table'),(HOOK,c.done(),'Independent NPC pointer hook'),
        (pc(0x009b8a),b'\x22'+cpu_address(HOOK).to_bytes(3,'little')+b'\x60'+b'\xea'*(len(ORIGINAL)-5),'NPC pointer dispatch')])
    return result
