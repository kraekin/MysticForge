"""Verified vanilla flag labels; never apply these to context/interpreter bits."""
from dataclasses import dataclass

NAMES={1:'Earth restored',2:'Water restored',3:'Fire restored',5:'Wind restored'}
BEHAVIOR_NAMES={0x04:'Spencer’s Cave entrance variant',0x13:'Level Forest entrance variant',
                0xf2:'Alternate monster graphics gate',0xf5:'Player pose flag'}
EVIDENCE='research/RESTORATION_STATES.md — vanilla restoration flags and area action lists'

def flag_label(value):
    if value in NAMES:return f'${value:02X} — {NAMES[value]}'
    if value in BEHAVIOR_NAMES:return f'${value:02X} — {BEHAVIOR_NAMES[value]} (verified use)'
    return f'${value:02X} (unnamed game flag)'

@dataclass(frozen=True)
class FlagUse:
    flag:int
    action:str
    address:int

def flag_uses(row):
    raw=row.raw
    if not row.complete or not raw:return ()
    op=raw[0];uses=[]
    if op in (0x23,0x2b,0x2e) and len(raw)>1:
        uses.append(FlagUse(raw[1],{0x23:'Set',0x2b:'Clear',0x2e:'Check'}[op],row.address))
    elif raw[:2] in (b'\x05\x0b',b'\x05\x12',b'\x05\x13') and len(raw)>2:
        uses.append(FlagUse(raw[2],'Check',row.address))
    # Native player-pose actions explicitly set/clear F5.
    words=[(1,raw[1:3])] if op==0x2c else [(i,raw[i:i+2]) for i in range(1,len(raw)-2,2)] if op==0x2a else []
    for offset,word in words:
        if len(word)==2 and word[1]==0x56 and word[0]>>4 in (9,10):
            uses.append(FlagUse(0xf5,'Set' if word[0]>>4==9 else 'Clear',row.address+offset))
    return tuple(uses)

def name_flags(description):
    import re
    return re.sub(r'game flag \$([0-9A-Fa-f]{2})(?![0-9A-Fa-f])',
                  lambda m:'game flag '+flag_label(int(m[1],16)),description)
