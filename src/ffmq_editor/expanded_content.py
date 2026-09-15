"""Bounded expanded content with stable logical IDs and guarded loader changes."""
from .rom import pc,FormatError
from .layout_storage import cpu_address

CONTENT_START=0xd8000
OBJECT_BASE=0xd8100
SET_BANK=0xe0000
DEST_BANK=0xe8000
COORD_BANK=0xf0000
META_HOOK=0xf8000
COORD_HOOK=0xf8100
KINDS={'metatile_graphics':('graphics',512),'metatile_attributes':('attributes',128),'properties':('properties',256)}

def empty():return {'sets':{},'entrances':{}}
def coordinate_id(i):return 0x200000+i*3
def destination_id(i):return 0x210000+i*3
def entrance_index(resource,base):
    if type(resource) is int and base<=resource<base+39*3 and (resource-base)%3==0:return (resource-base)//3
    return None

def active(p):
    return bool(p.sprite_sets or p.newmaps or p.content['sets'] or p.content['entrances'] or any(k=='object_count' and v>p.rom.object_capacities[r] for (k,r,i),v in p.edits.items()))

def validate(p):
    if not isinstance(p.content,dict) or set(p.content)!={'sets','entrances'}:raise FormatError('Invalid expanded content')
    if not all(isinstance(v,dict) for v in p.content.values()):raise FormatError('Invalid expanded content tables')
    for (kind,resource,index),value in p.edits.items():
        if kind=='object_count':
            area=next((a for a in p.rom.areas if a.offset==resource),None)
            if area is None or type(value) is not int or not 0<=value<=p.object_capacity(area.id):raise FormatError('Object count exceeds this profile')
    areas=set()
    for key,c in p.content['sets'].items():
        if type(key) is not int or not 16<=key<32 or not isinstance(c,dict) or set(c)!={'area','graphics','attributes','properties'}:raise FormatError('Invalid private metatile set')
        if type(c['area']) is not int or not 0<=c['area']<len(p.rom.areas) or c['area'] in areas:raise FormatError('Invalid metatile configuration')
        areas.add(c['area'])
        for field,size in KINDS.values():
            if not isinstance(c[field],bytes) or len(c[field])!=size:raise FormatError('Invalid private metatile data')
    seen=set()
    for key,c in p.content['entrances'].items():
        if type(key) is not int or not 0<=key<39 or not isinstance(c,dict) or set(c)!={'area','x','y','target'}:raise FormatError('Invalid new entrance')
        if type(c['area']) is not int or not 0<=c['area']<len(p.rom.areas):raise FormatError('Invalid entrance area')
        a=p.rom.areas[c['area']];attrs=p.rom.attributes[a.attributes_id]
        if a.layout_id==0 or any(type(c[k]) is not int for k in ('x','y')) or not 0<=c['x']<attrs.width or not 0<=c['y']<attrs.height:raise FormatError('Invalid entrance position')
        if not isinstance(c['target'],bytes) or len(c['target'])!=3:raise FormatError('Invalid entrance destination')
        position=(c['area'],*p.fixed('coordinate',coordinate_id(key))[:2])
        x,y,value=p.fixed('coordinate',coordinate_id(key))
        if x>=attrs.width or y>=attrs.height or (value>=217 and value-217 not in (set(p.content['entrances'])|{c['entry'] for c in p.newmaps.values()})):raise FormatError('Invalid new entrance coordinate or link')
        if position in seen:raise FormatError('Two new entrances occupy the same coordinate')
        seen.add(position)
        area,y,x=p.fixed('destination',destination_id(key))
        if area>=len(p.rom.areas):raise FormatError('Invalid entrance target area')
        target=p.rom.attributes[p.rom.areas[area].attributes_id]
        if y>=target.height or x&63>=target.width:raise FormatError('Entrance target is outside the map')
    if active(p) and not p.expanded:raise FormatError('Extra objects, new entrances and private metatiles require expanded export')

def copy_metatiles(p,area_id):
    if not p.expanded:raise FormatError('Enable expanded ROM export first')
    if type(area_id) is not int or not 0<=area_id<len(p.rom.areas):raise FormatError('Invalid map configuration')
    if p.tileset(area_id)>=16:raise FormatError('This configuration already has private metatiles')
    resource=next((i for i in range(16,32) if i not in p.content['sets']),None)
    if resource is None:raise FormatError('All 16 private metatile slots are used')
    source=p.tileset(area_id)
    p.content['sets'][resource]={'area':area_id,**{field:p.fixed(kind,source) for kind,(field,size) in KINDS.items()}}
    return resource

def add_entrance(p,area_id,x,y,target,tile):
    if not p.expanded:raise FormatError('Enable expanded ROM export first')
    if type(area_id) is not int or not 0<=area_id<len(p.rom.areas):raise FormatError('Invalid source area')
    area=p.rom.areas[area_id];attrs=p.rom.attributes[area.attributes_id]
    if area.layout_id==0 or not 0<=x<attrs.width or not 0<=y<attrs.height:raise FormatError('Choose a position on a field map')
    if len(target)!=3 or target[0]>=len(p.rom.areas):raise FormatError('Invalid target')
    dest=p.rom.attributes[p.rom.areas[target[0]].attributes_id]
    if target[1]>=dest.height or (target[2]&63)>=dest.width:raise FormatError('Destination is outside its map')
    if not 0<=tile<=255:raise FormatError('Invalid door tile')
    props=bytearray(p.fixed('properties',p.tileset(area_id)))
    state=p.state(area_id)
    for a,b in state.remaps:props[a*2:a*2+2]=props[b*2:b*2+2]
    if props[(tile&127)*2+1]!=0x80:raise FormatError('Select a normal door tile (transition action 0) in Tiles before adding an entrance')
    for action in state.applied:
        if action.opcode==0x22:
            c=p.rom.changes[action.value]
            if c.x<=x<c.x+c.width and c.y<=y<c.y+c.height:raise FormatError('A story-state terrain patch covers this position; choose an uncovered position')
    for i,e in p.content['entrances'].items():
        if e['area']==area_id and tuple(p.fixed('coordinate',coordinate_id(i))[:2])==(x,y):raise FormatError('A new entrance already occupies this position')
    resource=next((i for i in range(39) if i not in p.content['entrances'] and i not in {c['entry'] for c in p.newmaps.values()}),None)
    if resource is None:raise FormatError('All 39 new entrance destination slots are used')
    p.content['entrances'][resource]={'area':area_id,'x':x,'y':y,'target':bytes(target)}
    p.set(('layout',p.layout_id(area_id),y*attrs.width+x),tile)
    return resource

def encode(p):
    return {'sets':[{'id':i,**{k:(v.hex() if isinstance(v,bytes) else v) for k,v in c.items()}} for i,c in sorted(p.content['sets'].items())],
            'entrances':[{'id':i,**c,'target':c['target'].hex()} for i,c in sorted(p.content['entrances'].items())]}

def decode(raw):
    result=empty()
    for category in result:
        for item in raw[category]:
            c=dict(item);i=c.pop('id')
            if i in result[category]:raise FormatError('Duplicate expanded content ID')
            for k in (('graphics','attributes','properties') if category=='sets' else ('target',)):c[k]=bytes.fromhex(c[k])
            result[category][i]=c
    return result

class Code:
    def __init__(self):self.data=bytearray();self.labels={};self.fixups=[]
    def emit(self,h):self.data.extend(bytes.fromhex(h))
    def branch(self,opcode,label):self.data.extend((opcode,0));self.fixups.append((len(self.data)-1,label))
    def label(self,name):self.labels[name]=len(self.data)
    def done(self):
        for pos,name in self.fixups:
            delta=self.labels[name]-pos-1
            if not -128<=delta<=127:raise FormatError('Native branch exceeds range')
            self.data[pos]=delta&255
        return bytes(self.data)

def writes(p):
    validate(p);rom=p.rom;result=[]
    def put(at,data,label):result.append((at,bytes(data),label))
    def guard(at,old,new,label):
        old=bytes.fromhex(old)
        if rom.data[pc(at):pc(at)+len(old)]!=old:raise FormatError('Expanded loader guard failed: '+label)
        if len(new)!=len(old):raise FormatError('Native patch width mismatch')
        put(pc(at),new,label)
    def long_operand(at,old,target,label):guard(at,old,cpu_address(target).to_bytes(3,'little'),label)
    # Repack complete area records; aliases retain one shared record and indexes.
    if p.sprite_sets or p.newmaps or any(k=='object_count' and v>rom.object_capacities[r] for (k,r,i),v in p.edits.items()):
        for at,old,target in [(0x0b81b0,'3baf07',CONTENT_START),(0x0b81bd,'13b007',OBJECT_BASE),(0x0190ef,'13b007',OBJECT_BASE)]:long_operand(at,old,target,'expanded object source')
        pointers=bytearray(256);cursor=OBJECT_BASE;by_offset={}
        for area in rom.areas:
            identity=(area.offset,area.header)
            if identity not in by_offset:
                by_offset[identity]=cursor-OBJECT_BASE
                header=bytearray(area.header);header[0]=(header[0]&192)|p.layout_id(area.id)
                data=header+b''.join(p.objects(area.id))+b'\xff'
                if cursor+len(data)>SET_BANK:raise FormatError('Expanded object bank full')
                put(cursor,data,f'expanded area/object record {area.id:02X}');cursor+=len(data)
            pointers[area.id*2:area.id*2+2]=by_offset[identity].to_bytes(2,'little')
        put(CONTENT_START,pointers,'expanded area pointer table')
    if p.content['sets']:
        expected=bytes.fromhex('8b4baba20000a0f4cead1819290fda48ebbdac838d1b21bdad838d1b21eb8d1c21c220bdb283186d342148bdac833afae2208b547f06ab68fae8e8e00600d0ceab6b')
        if rom.data[pc(0x0b836a):pc(0x0b836a)+len(expected)]!=expected:raise FormatError('Metatile base loader guard failed')
        # Original loader executes first; overlay private definitions while preserving its output registers.
        guard(0x01915d,'226a830b',b'\x22'+cpu_address(META_HOOK).to_bytes(3,'little'),'private metatile overlay call')
        table=bytearray(256);cursor=SET_BANK+256
        for i,c in sorted(p.content['sets'].items()):
            table[2*c['area']:2*c['area']+2]=(cpu_address(cursor)&65535).to_bytes(2,'little')
            put(cursor,b''.join(p.fixed(k,i) for k in KINDS),f'private metatile set {i:02X}');cursor+=896
        put(SET_BANK,table,'private metatile area table')
        c=Code();c.emit('226a830b 08 c230 48 da 5a 8b af910e00 29ff00 0a aa')
        c.emit('bf'+cpu_address(SET_BANK).to_bytes(3,'little').hex());c.branch(0xf0,'end')
        c.emit('aa a0f4ce a97f03 547f1c');c.label('end');c.emit('ab 7a fa 68 28 6b')
        put(META_HOOK,c.done(),'private metatile overlay routine')
    if p.content['entrances'] or p.newmaps:
        # Preserve short-B/long record low addresses; short-A gains 39 slots at $1D8000.
        copied=bytearray(rom.data[pc(0x05f4a0):pc(0x05f920)])
        for base,count,size in ((0x05f79a,86,3),(0x05f89c,33,4)):
            for i in range(count):
                offset=pc(base)+i*size;relative=offset-pc(0x05f4a0)
                copied[relative:relative+size]=p.fixed('destination',offset)
        put(DEST_BANK+0x74a0,copied,'copied destination tables')
        table=bytearray(256*3)
        for i in range(217):table[i*3:i*3+3]=p.fixed('destination',pc(0x05f4a0)+i*3)
        for i in set(p.content['entrances'])|{c['entry'] for c in p.newmaps.values()}:table[(217+i)*3:(218+i)*3]=p.fixed('destination',destination_id(i))
        put(DEST_BANK,table,'expanded short-A destinations')
        guard(0x01b29d,'a0f4',b'\x00\x80','short-A table offset')
        guard(0x01b2bc,'0500',b'\x1d\x00','short destination bank')
        guard(0x01b35d,'0500',b'\x1d\x00','long destination bank')
        # Private overrides are consulted before the original coordinate lookup.
        old=rom.data[pc(0x01f387):pc(0x01f3b4)]
        expected=bytes.fromhex('8ba90548abad910e0ac22029ff00aabf20f905aae220bcf8f9cc2b19d008bdfaf98dee198006e8e8e89810eaab')
        if old!=expected:raise FormatError('Coordinate scan guard failed')
        guard(0x01f387,'8ba90548',b'\x5c'+cpu_address(COORD_HOOK).to_bytes(3,'little'),'new entrance lookup hook')
        pointers=bytearray(256);cursor=COORD_BANK+256
        for area in rom.areas:
            entries=[i for i,e in sorted(p.content['entrances'].items()) if e['area']==area.id]
            if not entries:continue
            pointers[area.id*2:area.id*2+2]=(cursor-COORD_BANK).to_bytes(2,'little')
            data=b''.join(p.fixed('coordinate',coordinate_id(i)) for i in entries)+b'\xff\xff\x00'
            put(cursor,data,f'new coordinates area {area.id:02X}');cursor+=len(data)
        put(COORD_BANK,pointers,'new entrance area table')
        c=Code();c.emit('08 c230 48 da 5a 8b ad910e 29ff00 0a aa bf00801e');c.branch(0xf0,'fallback')
        c.emit('aa');c.label('scan');c.emit('bf00801e c9ffff');c.branch(0xf0,'fallback')
        c.emit('cd2b19');c.branch(0xf0,'found');c.emit('e8e8e8');c.branch(0x80,'scan')
        c.label('found');c.emit('e220 bf02801e 8dee19 9cef19 ab c230 7a fa 68 28 38 adee19 5cb4f301')
        c.label('fallback')
        if p.newmaps:
            c.emit('af910e00 29ff00 c96c00');c.branch(0x90,'original')
            c.emit('ab 7a fa 68 28 adee19 5cb4f301')
            c.label('original')
        c.emit('ab 7a fa 68 28');c.data.extend(old);c.emit('5cb4f301')
        put(COORD_HOOK,c.done(),'new entrance lookup routine')
    return result
