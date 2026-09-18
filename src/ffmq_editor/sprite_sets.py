"""Private field sprite descriptors, bounded slot allocation and native export."""
from .rom import pc,u16,FormatError
TABLE=0xf8800
DATA=0xf8a00
END=0xfc000
COUNT=53
LOADS=(0x01a459,0x01a505,0x01a524,0x01a55d)

def original(rom,selector):
    if selector==255:return bytes(12)
    if not 0<=selector<COUNT:raise FormatError('Invalid original sprite set')
    start=pc(0x0b88fc)+u16(rom.data,pc(0x0b8892)+selector*2)
    mask=rom.data[start+6:start+12]
    size=12+sum(bool(mask[i//8]&(128>>(i%8))) for i in range(44))
    return bytes(rom.data[start:start+size])

def descriptor(rom,area):
    selector=rom.areas[area].header[2]
    return getattr(rom,'sprite_descriptors',{}).get(selector) or original(rom,selector)

def unpack(raw):
    entries={};cursor=12
    for i in range(44):
        if raw[6+i//8]&(128>>(i%8)):entries[i]=raw[cursor];cursor+=1
    return list(raw[:6]),entries,raw[11]&15

def pack(palettes,entries,flags):
    raw=bytearray(palettes)+bytearray(6);raw[11]=flags
    for i in sorted(entries):raw[6+i//8]|=128>>(i%8)
    return bytes(raw)+bytes(entries[i] for i in sorted(entries))

def slots(rom):return [0x90+u16(rom.data,pc(0x01a5df)+i*2)//32 for i in range(44)]

def frames(rom,obj):
    behavior=((obj[2]&192)>>1)|(obj[4]&31)
    at=pc(0x0b87e4)+behavior*2;b0,b1=rom.data[at:at+2];animation=b0&63
    base=pc(0x00f141)+u16(rom.data,pc(0x00fdcf)+animation*2)
    result=[]
    for facing in range(4):
        for pose in range((b1&3)+1 if b1>>6==2 else 1):
            at=base+facing*(16 if animation<5 else 8)+pose*8
            for tile,attr in zip(rom.data[at:at+8:2],rom.data[at+1:at+8:2]):
                result.append(((tile+(obj[6]&127)*4+((attr&1)<<8))&511,attr))
    return result

def appearance(raw,source):
    """Keep coordinates, visibility, interaction and traversal; copy sprite/pose behavior."""
    obj=bytearray(raw);obj[2]=(obj[2]&63)|(source[2]&192);obj[4]=source[4];obj[6]=(obj[6]&128)|(source[6]&127)
    return bytes(obj)

def interaction(raw,source):
    obj=bytearray(raw);obj[1]=source[1];obj[5]=(obj[5]&~24)|(source[5]&24)
    return bytes(obj)

def validate(p):
    if p.sprite_sets and not p.expanded:raise FormatError('Private sprite sets require expanded export')
    for area,c in p.sprite_sets.items():
        if type(area) is not int or not 0<=area<len(p.rom.areas) or p.rom.areas[area].layout_id==0:raise FormatError('Invalid sprite-set area')
        if not isinstance(c,dict) or set(c)!={'data','presets','base','labels'}:raise FormatError('Invalid private sprite set')
        if type(c['base']) is not int or c['base'] not in (*range(COUNT),255):raise FormatError('Invalid source sprite set')
        if not isinstance(c['labels'],list) or len(c['labels'])!=len(c['presets']) or any(not isinstance(t,str) or len(t)>160 for t in c['labels']):raise FormatError('Invalid imported sprite labels')
        raw=c['data']
        if not isinstance(raw,bytes) or not 12<=len(raw)<=56:raise FormatError('Invalid sprite descriptor')
        try:pal,entries,flags=unpack(raw)
        except IndexError as e:raise FormatError('Truncated sprite descriptor') from e
        if pack(pal,entries,flags)!=raw or any(n>=(0xddc4-0xd824)//16 for n in pal):raise FormatError('Invalid sprite palette or presence table')
        if not isinstance(c['presets'],list) or len(c['presets'])>128 or any(not isinstance(o,bytes) or len(o)!=7 or o[0]==255 for o in c['presets']):raise FormatError('Invalid imported sprite presets')

def choose(p,area,source):
    if not p.expanded:raise FormatError('Enable expanded export first')
    if not 0<=source<108 or p.base_rom.areas[source].layout_id==0:raise FormatError('Choose a field-map sprite set')
    if p.base_rom.areas[source].header[2]==255:raise FormatError('This configuration does not load a sprite set')
    p.sprite_sets[area]={'data':original(p.base_rom,p.base_rom.areas[source].header[2]),'presets':[],'labels':[],'base':p.base_rom.areas[source].header[2]}
    from .new_maps import sync_catalog
    sync_catalog(p);p.validate_expansion()

def import_sprite(p,area,source,obj):
    """Find a slot/palette without changing any existing object's frame data."""
    import numpy as np
    from .sprites import Sprites
    if not p.expanded:raise FormatError('Enable expanded export first')
    if p.rom.areas[area].layout_id==0:raise FormatError('Use Artwork for overworld sprites')
    if p.rom.areas[area].header[2]==255:raise FormatError('This map does not load sprites yet. Choose a complete sprite set first, then add individual sprites.')
    raw=descriptor(p.rom,area);pal,entries,flags=unpack(raw)
    source_raw=original(p.base_rom,p.base_rom.areas[source].header[2]);spal,sentries,sflags=unpack(source_raw)
    src_tiles,_=Sprites(p.base_rom).field_set(source);dst_tiles,_=Sprites(p.rom).field_set(area)
    poses=frames(p.base_rom,obj);needed={t for t,_ in poses};starts=slots(p.base_rom)
    if any(t>=0x180 for t in needed) and (flags^sflags)&1:raise FormatError('This sprite requires a different shared monster/boss sheet. Choose the complete sprite set instead.')
    protected=list(p.objects(area))+p.sprite_sets.get(area,{}).get('presets',[])
    used_tiles={t for o in protected for t,_ in frames(p.rom,o)}
    used_colors={((o[4]>>5)|((attr>>1)&7)) for o in protected for _,attr in frames(p.rom,o)}
    # First try existing resident graphics. Otherwise move one complete graphics block.
    choices=[(0,dict(entries))] if all(np.array_equal(src_tiles[t],dst_tiles[t]) for t in needed) else []
    for s,g in sentries.items():
        if g==255:continue
        size=8 if g&128 else 16;block=set(range(starts[s],starts[s]+size))
        if not needed<=block:continue
        for target,start in enumerate(starts):
            delta=start-starts[s];sprite=(obj[6]&127)+delta//4;region=set(range(start,start+size))
            if not 0<=sprite<128 or max(region)>=0x180 or region&used_tiles:continue
            updated=dict(entries);valid=True
            for other,value in entries.items():
                overlap=set(range(starts[other],starts[other]+(8 if value&128 else 16)))
                if region&overlap:
                    if overlap&used_tiles:valid=False;break
                    del updated[other]
            if valid:updated[target]=g;choices.append((delta,updated))
    full_spal=spal+[1,0]
    for delta,updated in choices:
        for palette in range(8):
            colors=pal+[1,0];valid=True;assigned={}
            for _,attr in poses:
                old=(obj[4]>>5)|((attr>>1)&7);new=palette|((attr>>1)&7);value=full_spal[old]
                if new in assigned and assigned[new]!=value:valid=False;break
                if colors[new]!=value and (new in used_colors or new>=5):valid=False;break
                assigned[new]=value;colors[new]=value
            if not valid:continue
            candidate=pack(colors[:6],updated,flags)
            # Reuse the actual renderer decoder to check overlapping slot writes.
            from copy import copy
            r=copy(p.rom);r.sprite_descriptors={**getattr(r,'sprite_descriptors',{}),r.areas[area].header[2]:candidate}
            tiles,_=Sprites(r).field_set(area)
            if not all(np.array_equal(src_tiles[t],tiles[(t+delta)&511]) for t in needed):continue
            if not all(np.array_equal(dst_tiles[t],tiles[t]) for t in used_tiles):continue
            imported=bytearray(obj);imported[6]=(obj[6]&128)|((obj[6]&127)+delta//4);imported[4]=(obj[4]&31)|(palette<<5)
            imported=bytes(imported);presets=list(p.sprite_sets.get(area,{}).get('presets',[]))
            labels=list(p.sprite_sets.get(area,{}).get('labels',[]))
            if imported not in presets:
                presets.append(imported);labels.append(f"{p.base_rom.areas[source].name} / sprite ${obj[6]&127:02X}")
            base=p.sprite_sets.get(area,{}).get('base',p.rom.areas[area].header[2])
            p.sprite_sets[area]={'data':candidate,'presets':presets,'labels':labels,'base':base}
            from .new_maps import sync_catalog
            sync_catalog(p);p.validate_expansion();return imported
    raise FormatError('No compatible free graphics/palette slots. Remove unused objects/presets or choose a different complete sprite set. Existing objects were not changed.')

def writes(p):
    if not p.sprite_sets:return []
    descriptors={i:original(p.base_rom,i) for i in range(COUNT)}
    descriptors.update({COUNT+a:c['data'] for a,c in p.sprite_sets.items()})
    table=bytearray(512);data=bytearray();offsets={}
    for i,raw in sorted(descriptors.items()):
        raw=bytes(raw)
        if raw not in offsets:offsets[raw]=len(data);data.extend(raw)
        table[i*2:i*2+2]=offsets[raw].to_bytes(2,'little')
    if DATA+len(data)>END:raise FormatError('Private sprite descriptor bank full')
    result=[(TABLE,bytes(table),'sprite descriptor pointers'),(DATA,bytes(data),'sprite descriptors')]
    for addr,old,target in [(0x0b8200,0x0b8892,0x1f8800)]+[(a,0x0b88fc,0x1f8a00) for a in LOADS]:
        at=pc(addr);expected=b'\xbf'+old.to_bytes(3,'little')
        if p.rom.data[at:at+4]!=expected:raise FormatError('Sprite descriptor loader guard failed')
        result.append((at,b'\xbf'+target.to_bytes(3,'little'),'sprite descriptor loader'))
    return result
