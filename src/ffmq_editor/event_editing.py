"""Fixed-span event edits. Original control-flow boundaries remain immutable.

This is deliberately not a relocating assembler: the original index is the
authority for writable spans, including when loading an untrusted project.
"""
from collections import deque
from copy import copy
from dataclasses import dataclass
import re
from hashlib import sha256
from .events import decode, fragments, npc_entry, world_entry, text_fragment
from .rom import pc, read, FormatError, BASE_SHA256

NAME_OPS = {'Character':(0x1d,9), 'Item':(0x1e,224), 'Location':(0x1f,37), 'Enemy':(0x20,81)}
SPECIAL = {'[Hero name]':bytes.fromhex('0518001008'),
           '[Companion name]':bytes.fromhex('0518801008'),
           '[Number]':bytes.fromhex('0518660008'),
           '[Spacing]':b'\x03', '[Line break or space]':b'\x06'}
GLYPHS = {text_fragment(bytes([b])):bytes([b]) for b in range(0x90,0x100)
          if not text_fragment(bytes([b])).startswith('[')}

def tokens(rom, raw, seen=frozenset()):
    """Readable source with explicit runtime inserts; None means executable code."""
    result=[];i=0;dictionary=fragments(rom)
    while i<len(raw):
        b=raw[i];i+=1
        if b>=0x80:
            text=text_fragment(bytes([b]));result.append(f'[Glyph:{b:02X}]' if text.startswith('[') else text)
        elif b in (1,2):result.append('\n'*b)
        elif b==3:result.append('[Spacing]')
        elif b==4:pass  # Verified no-op; padding is never displayed.
        elif b==6:result.append('[Line break or space]')
        elif b in (0x1d,0x1e,0x1f,0x20):
            name,(_,count)=next((n,v) for n,v in NAME_OPS.items() if v[0]==b)
            if i==len(raw) or raw[i]>=count:return None
            result.append(f'[{name}:{raw[i]:02X}]');i+=1
        elif b==5:
            match=next(((name,value) for name,value in SPECIAL.items() if value[0]==5 and raw[i-1:i-1+len(value)]==value),None)
            if match:result.append(match[0]);i+=len(match[1])-1
            elif raw[i:i+1]==b'\x75' and i+1<len(raw) and raw[i+1]>=0x80:
                result.append(f'[Draw glyph:{raw[i+1]:02X}]');i+=2
            else:return None
        elif 0x30<=b<0x7f:
            if b in seen:return None
            at,n=dictionary[b-0x30];part=tokens(rom,read(rom.data,pc(at),n),seen|{b})
            if part is None:return None
            result.append(part)
        else:return None
    return ''.join(result)

def atomize(text):
    parts=re.findall(r'\[[^\]\n]*\]|.',text.replace('\r\n','\n'),re.DOTALL)
    if ''.join(parts)!=text.replace('\r\n','\n'):raise FormatError('Invalid text token')
    return tuple(parts)

def atom_bytes(atom):
    if atom=='\n':return b'\x01'
    if atom in SPECIAL:return SPECIAL[atom]
    if atom in GLYPHS:return GLYPHS[atom]
    match=re.fullmatch(r'\[(Character|Item|Location|Enemy|Glyph|Draw glyph):([0-9A-Fa-f]{2})\]',atom)
    if match:
        name,index=match[1],int(match[2],16)
        if name=='Glyph' and 0x80<=index<=255:return bytes([index])
        if name=='Draw glyph' and 0x80<=index<=255:return bytes([5,0x75,index])
        if name in NAME_OPS and index<NAME_OPS[name][1]:return bytes([NAME_OPS[name][0],index])
    raise FormatError(f'Unsupported character or token: {atom!r}. Use the token picker or game glyph reference.')

def encode_text(rom,text):
    if len(text)>8192:raise FormatError('Dialogue segment exceeds 8,192 characters')
    atoms=atomize(text)
    # Validate before dictionary matching; arbitrary command bytes cannot be typed.
    singles=[atom_bytes(a) for a in atoms]
    options=[(atomize(s),v) for s,v in GLYPHS.items() if len(s)>1]
    options.append((('\n','\n'),b'\x02'))
    for index,(at,n) in enumerate(fragments(rom)):
        # Match source tokens, not flattened display text: formatting and name
        # helpers must remain exactly the same operations after compression.
        raw=read(rom.data,pc(at),n)
        source=tokens(rom,raw)
        if source:options.append((atomize(source),bytes([index+0x30])))
    best=[None]*(len(atoms)+1);best[-1]=b''
    for i in range(len(atoms)-1,-1,-1):
        candidates=[singles[i]+best[i+1]]
        for pattern,value in options:
            if atoms[i:i+len(pattern)]==pattern:candidates.append(value+best[i+len(pattern)])
        best[i]=min(candidates,key=lambda b:(len(b),b))
    return best[0]

@dataclass(frozen=True)
class Segment:
    address:int
    raw:bytes
    kind:str
    label:str
    operand:int=0
    maximum:int=255
    minimum:int=0

def parameter(row):
    raw=row.raw
    if not row.complete or not raw:return None
    op=raw[0]
    if op in (0x23,0x2b,0x2e):return ('Flag ID',1,255,0)
    if raw[:2]==b'\x05\x0b':return ('Flag ID',2,255,0)
    if raw[:2]==b'\x05\xe1':return ('Wait (frames)',2,255,1)
    # Calls, branch targets, native memory writes and context-dependent commands
    # are preserved. Editing them requires a separate validated assembler.
    return None

class EditIndex:
    def __init__(self,rom):
        self.rom=rom;dictionary=dict(fragments(rom));queue=deque()
        roots={npc_entry(rom,i) for i in range(124)}|{world_entry(rom,i) for i in range(80)}|{0x038686}|set(dictionary)
        roots.discard(None);queue.extend((a,dictionary.get(a)) for a in roots)
        seen=set();variants={};incoming=set(roots);total=0
        while queue:
            key=queue.popleft()
            if key in seen:continue
            seen.add(key)
            if len(seen)>4096 or total>250000:raise FormatError('Event index exceeded its verification limit')
            rows=decode(rom,key[0],limit=8192,follow_calls=False,extent=key[1]);total+=len(rows)
            for row in rows:
                if 'Inspection limit' in row.description:raise FormatError('Event indexing was incomplete')
                if row.raw:variants.setdefault(row.address,{})[row.raw]=row
                for label,target in row.edges:
                    if label=='next':continue
                    incoming.add(target)
                    extent=row.raw[-1] if label=='bounded' else dictionary.get(target)
                    if label not in ('call','fragment','bounded') and key[1] is not None and key[0]<=target<key[0]+key[1]:extent=key[0]+key[1]-target
                    queue.append((target,extent))
        self.entries=seen;self.incoming=incoming;self.segments={};self.rows={a:next(iter(v.values())) for a,v in variants.items() if len(v)==1}
        # Exclude dictionary bodies (global compression dependency) and every
        # overlapping interpretation, including incoming jumps into text runs.
        owners={}
        for a,choices in variants.items():
            for raw in choices:
                for byte in range(a,a+len(raw)):owners.setdefault(byte,set()).add(a)
        def eligible(row):
            a=row.address
            return (row.complete and not 0x03ba86<=a<0x03bbd2 and
                    all(len(owners[b])==1 for b in range(a,a+len(row.raw))) and
                    not any(t in incoming for t in range(a+1,a+len(row.raw))))
        group=[]
        def flush():
            if group:
                raw=b''.join(r.raw for r in group)
                if tokens(rom,raw):self.segments[group[0].address]=Segment(group[0].address,raw,'text','Dialogue')
                group.clear()
        for a,row in sorted(self.rows.items()):
            if not eligible(row):flush();continue
            text=tokens(rom,row.raw)
            if text is not None:
                if group and (group[-1].address+len(group[-1].raw)!=a or a in incoming):flush()
                group.append(row)
            else:
                flush();field=parameter(row)
                if field:self.segments[a]=Segment(a,row.raw,'parameter',row.description,field[1],field[2],field[3])
        flush()

def index(project):
    base=project.base_rom;cached=getattr(base,'_event_edit_index',None)
    if sha256(base.data).hexdigest()!=BASE_SHA256:raise FormatError('Event editing requires the verified original USA v1.0 base ROM')
    if cached is None or cached[0] is not base.data:
        cached=(base.data,EditIndex(base));base._event_edit_index=cached
    return cached[1]

def event_rom(project):
    if not project.event_edits:return project.rom
    signature=(id(project.rom),tuple((a,r['bytes']) for a,r in sorted(project.event_edits.items())))
    cached=getattr(project,'_event_overlay',None)
    if cached is not None and cached[0]==signature:return cached[1]
    result=copy(project.rom);data=bytearray(result.data)
    for at,record in project.event_edits.items():
        raw=bytes.fromhex(record['bytes']);data[pc(at):pc(at)+len(raw)]=raw
    result.data=bytes(data);project._event_overlay=(signature,result);return result

def view_rom(window):
    """Keep standalone read-only viewers usable without an editing project."""
    return event_rom(window.project) if hasattr(window,'project') else window.rom

def replacement(project,segment,value):
    if segment.kind=='text':
        if not isinstance(value,str):raise FormatError('Dialogue must be text')
        if value==tokens(project.base_rom,segment.raw):return segment.raw
        raw=encode_text(project.base_rom,value)
        if len(raw)>len(segment.raw):raise FormatError(f'This text needs {len(raw)} bytes; its protected span holds {len(segment.raw)}. Shorten the text. Event relocation is not enabled yet.')
        return raw+b'\x04'*(len(segment.raw)-len(raw))
    if type(value) is not int or not segment.minimum<=value<=segment.maximum:raise FormatError('Event parameter is outside its allowed range')
    raw=bytearray(segment.raw);raw[segment.operand]=value;return bytes(raw)

def change(project,address,value):
    segment=index(project).segments.get(address)
    if segment is None:raise FormatError('This event span is not editable')
    raw=replacement(project,segment,value)
    if raw==segment.raw:project.event_edits.pop(address,None)
    else:project.event_edits[address]={'value':value,'bytes':raw.hex()}

def validate(project):
    if not isinstance(project.event_edits,dict):raise FormatError('Invalid event edits')
    if not project.event_edits:return
    if sha256(project.rom.data).hexdigest()!=BASE_SHA256:raise FormatError('Original ROM bytes changed; refusing event export')
    segments=index(project).segments
    for address,record in project.event_edits.items():
        if type(address) is not int or address not in segments or not isinstance(record,dict) or set(record)!={'value','bytes'}:raise FormatError('Invalid event edit record')
        s=segments[address]
        if replacement(project,s,record['value']).hex()!=record['bytes']:raise FormatError('Event bytes do not match the validated text or parameter')
        if read(project.rom.data,pc(address),len(s.raw))!=s.raw:raise FormatError('Original event bytes changed; refusing export')

def writes(project):
    validate(project)
    return [(pc(a),bytes.fromhex(r['bytes']),f'Event edit ${a:06X}') for a,r in sorted(project.event_edits.items())]

def segments_for(project,entry,extent=None):
    rows=decode(project.base_rom,entry,limit=8192,follow_calls=False,extent=extent)
    addresses={r.address for r in rows};result=[]
    for a,s in sorted(index(project).segments.items()):
        if a in addresses and (extent is None or entry<=a and a+len(s.raw)<=entry+extent):result.append(s)
    return result
