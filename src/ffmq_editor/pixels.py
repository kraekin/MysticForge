"""Packed terrain graphics and physical sharing, independent of loaded slot aliases."""
import numpy as np
from .rom import FormatError
from .render import decode_3bpp


def encode_3bpp(pixels):
    a=np.asarray(pixels)
    if a.shape!=(8,8) or a.dtype.kind not in 'iu' or np.any(a<0) or np.any(a>7):
        raise FormatError('A terrain graphic must contain 8 × 8 color indices from 0 to 7')
    raw=bytearray(24)
    for y in range(8):
        for x in range(8):
            value=int(a[y,x]);bit=7-x
            raw[y*2]|=(value&1)<<bit;raw[y*2+1]|=((value>>1)&1)<<bit;raw[16+y]|=((value>>2)&1)<<bit
    return bytes(raw)


def resource_for(rom,area_id,slot):
    if type(slot) is not int or not 0<=slot<256:raise FormatError('Graphic slot must be 00–FF')
    selector=rom.attributes[rom.areas[area_id].attributes_id].raw[2+slot//32]
    if selector&128:return None
    if selector>=34:raise FormatError('Graphic selector is outside the verified terrain library')
    return selector*32+slot%32


def pixel_changes(project,resource,pixels):
    raw=encode_3bpp(pixels);old=project.fixed('terrain_graphic',resource)
    return {('terrain_graphic',resource,i):(a,b) for i,(a,b) in enumerate(zip(old,raw)) if a!=b}


def references(project,resource,animation):
    result=[]
    for area in project.rom.areas:
        slots=[s for s in range(256) if resource_for(project.rom,area.id,s)==resource]
        if not slots:continue
        attr=project.rom.attributes[area.attributes_id];raw=project.fixed('metatile_graphics',project.tileset(area.id))
        uses=[(t,q) for t in range(128) for q in range(4) if raw[t*4+q] in slots]
        notes=[]
        for destination,period,operation,sequence in animation.tile_program(area.header[3]>>4):
            if destination in slots:notes.append(f'slot ${destination:02X} is '+('replaced by animation' if operation==0 else 'scrolled by animation'))
            if any(s in sequence for s in slots):notes.append(f'used as animation artwork for slot ${destination:02X}')
        result.append((area.id,slots,uses,notes))
    return result
