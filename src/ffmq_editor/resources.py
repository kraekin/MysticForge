"""Fixed, verified ROM spans exposed by the content editors."""
from .rom import pc,FormatError

DESTINATIONS=((0x05F4A0,217,3),(0x05F79A,86,3),(0x05F72B,37,3),(0x05F89C,33,4))

# Overworld/field enemy sprite sheets ($04ADA0 monster, $04BE20 boss) exist but
# the field-sprite editor was removed (raw tiles, wrong palettes, not composed).
# Only BATTLE enemy sprites are edited here.






# (removed: overworld/field enemy sprite editor)



# In-battle enemy art (the large sprites shown during fights), verified against
# a live VRAM dump: a 5-byte-per-entry pointer table in bank $09, with each
# enemy's tiles stored as contiguous 3bpp (24-byte) tiles in banks $09-$0B.
BATTLE_TABLE_FILE=0x48460              # SNES $098460; entries x 5 bytes
BATTLE_TABLE_REAL=81                   # entries 0-80 are real enemies; 81-82 are junk
BATTLE_TABLE_BYTES=BATTLE_TABLE_REAL*5 # protect only the real pointer entries
BATTLE_ENEMY_COUNT=83
BATTLE_BANK_RANGE=(0x48000,0x5eb4c)    # banks $09-$0B enemy art; dark-king block = 598 tiles

def battle_enemy_entries(data):
    """[(enemy_id, file_offset, flags)] for the 83 table entries."""
    out=[]
    for i in range(BATTLE_ENEMY_COUNT):
        e=data[BATTLE_TABLE_FILE+i*5:BATTLE_TABLE_FILE+i*5+5]
        addr=e[0]|(e[1]<<8); bank=e[2]; flags=e[3]
        out.append((i, bank*0x8000+(addr-0x8000), flags))
    return out

def battle_owned_ends(entries):
    """pointer -> exclusive end (next distinct pointer), clamped to the battle
    bank range so a bogus trailing pointer can't produce an out-of-range span."""
    lo, hi = BATTLE_BANK_RANGE
    pts = sorted(set(off for _, off, _ in entries if lo <= off < hi))
    ends = {}
    for k, p in enumerate(pts):
        nxt = pts[k+1] if k+1 < len(pts) else hi
        ends[p] = min(nxt, hi)
    return ends

def in_battle_table(off):
    return BATTLE_TABLE_FILE<=off<BATTLE_TABLE_FILE+BATTLE_TABLE_BYTES









def span(kind,resource):
    from .database import TABLES
    if kind in TABLES:
        address,count,size=TABLES[kind]
        if type(resource) is int and 0<=resource<count:return pc(address)+resource*size,size
        raise FormatError("Database record is outside its verified table")
    if kind=="terrain_graphic" and 0<=resource<34*32:return pc(0x058C80)+resource*24,24

    if kind=="battle_graphic":
        lo,hi=BATTLE_BANK_RANGE
        if not lo<=resource<hi or resource+24>hi:raise FormatError("Battle graphic is outside the verified battle banks")
        if in_battle_table(resource):raise FormatError("Battle graphic overlaps the enemy pointer table")
        return resource,24
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
