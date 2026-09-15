"""Fixed, verified ROM spans exposed by the content editors."""
from .rom import pc,FormatError

DESTINATIONS=((0x05F4A0,217,3),(0x05F79A,86,3),(0x05F72B,37,3),(0x05F89C,33,4))

def span(kind,resource):
    from .database import TABLES
    if kind in TABLES:
        address,count,size=TABLES[kind]
        if type(resource) is int and 0<=resource<count:return pc(address)+resource*size,size
        raise FormatError("Database record is outside its verified table")
    if kind=="metatile_graphics" and 0<=resource<16:return pc(0x068000)+resource*512,512
    if kind=="metatile_attributes" and 0<=resource<16:return pc(0x06A000)+resource*128,128
    if kind=="properties" and 0<=resource<16:return pc(0x06A800)+resource*256,256
    if kind=="destination":
        for base,count,size in DESTINATIONS:
            start=pc(base)
            if start<=resource<start+count*size and (resource-start)%size==0:return resource,size
    if kind=="world_node" and 1<=resource<=56:return pc(0x07F7C3)+resource*2,2
    if kind=="world_gate" and 1<=resource<=56:return pc(0x07EE85)+resource*5,4
    if kind=="treasure" and 0<=resource<251:return pc(0x018000)+resource,1
    if kind=="encounter" and 0<=resource<207:return pc(0x02CE12)+resource*3,3
    if kind=="formation" and 0<=resource<234:return pc(0x02CA6A)+resource*4,4
    if kind=="world_action" and 0x16<=resource<0x38:return pc(0x07EFCB)+(resource-0x16)*2,2
    raise FormatError("Unknown fixed resource")

def changes(project,kind,resource,data):
    return {(kind,resource,i):(project.get((kind,resource,i)),value)
            for i,value in enumerate(data) if project.get((kind,resource,i))!=value}

def terrain_passage(properties,level):
    """Static ordinary-step terrain gate at local $01EAD4; not full movement."""
    target=properties&7
    return target==0 or (target!=7 and (level==0 or target==level or (level==1 and bool(properties&8))))
