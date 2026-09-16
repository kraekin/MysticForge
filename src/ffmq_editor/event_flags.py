"""Verified vanilla flag labels; never apply these to context/interpreter bits."""
from dataclasses import dataclass

NAMES={1:'Earth restored',2:'Water restored',3:'Fire restored',5:'Wind restored'}


BEHAVIOR_NAMES = {
    # Existing & Restoration Inverse Pairs
    0x04: 'Spencer’s Cave entrance variant',
    0x06: 'Foresta withered (cleared on Earth restored)',
    0x07: 'Aquaria frozen (cleared on Water restored)',
    0x08: 'Fireburg pre-restoration (cleared on Fire restored)',
    0x09: 'Windia pre-restoration (cleared on Wind restored)',

    # Foresta / Level Forest / Early Game
    0x12: 'Ice Golem defeated (vanilla milestone)',
    0x13: 'Level Forest completed / Old Man saved',
    0x14: 'Tree Wither received from Old Man',
    0x15: 'Kaeli healthy / Level Forest Minotaur phase (cleared when poisoned)',

    0x1D: 'Giant Tree set',
    0x1E: 'Minotaur defeated',
    0x1F: 'Kaeli cured with Elixir(unlocks focus tower route)',

    # Sand Temple & Overworld
    0x20: 'Sand Temple column unmoved',
    0x21: 'Sand Temple column moved',
    0x22: 'Hill of Destiny collapsed',
    0x23: 'Sand Coin used at Sand Temple',

    0x2C: 'Focus Tower Earth Door open',

    0x30: 'Focus Tower Earth Door closed',

    # Boulders & Terrain Obstacles
    0x34: 'Level Forest boulder obstacle active',
    0x35: 'Wintry Cave collapsed',
    0x36: 'Fireburg boulder in blocking position',

    0x3A: 'Giant Tree unset',
    0x3D: 'Pazuzu bridge shown',

    # Pazuzu's Tower Elevator & Floor States ($40 - $49)
    0x40: 'Pazuzu Tower 1F elevator state',
    0x41: 'Pazuzu Tower 2F elevator state',
    0x42: 'Pazuzu Tower 3F elevator state',
    0x43: 'Pazuzu Tower 4F elevator state',
    0x44: 'Pazuzu Tower 5F elevator state',
    0x45: 'Pazuzu Tower 6F elevator state',
    0x46: 'Pazuzu Tower 7F elevator state',
    0x47: 'Pazuzu Tower 2F switch flipped',
    0x48: 'Pazuzu Tower 4F switch flipped',
    0x49: 'Pazuzu Tower 6F switch flipped',

    # Mid-Game Progression & Towns
    0x4D: 'Phoebe house visited',
    0x4E: 'Phoebe present in Libra Temple',
    0x4F: 'Wakewater used on Aquaria',

    0x5A: 'Tristam present in Sand Temple',
    0x5B: 'River Coin used',
    0x5C: 'Boulder rolled',
    0x5D: 'Medusa defeated',

    0x62: 'Kaeli at her home in Foresta',
    0x63: 'Enable Minotaur fight',
    0x64: 'Volcano erupted',

    0x6C: 'Mysterious Man present in forest',
    0x6D: 'Hide diseased tree in Level Forest',
    0x6E: 'Talk to Tristam',
    0x6F: 'Elixir given to Kaeli',

    0x70: 'Talk to Phoebe',
    0x73: 'Exit Fall Basin',
    0x74: 'Talk to Grenade Guy',

    0x7A: 'Prologue complete',
    0x7D: 'Kaeli sick in bed',

    # Late-Game / Special Triggers
    0xB3: 'Fall Basin chest spawned',

    0xC9: 'Tristam departs from Bone Dungeon (leaving party)',

    0xCB: 'Mysterious Man present in Focus Tower cave',

    0xCF: 'Rainbow Road active',

    0xDB: 'Tristam present in Bone Dungeon (boss room)',

    0xE0: 'Squid defeated',

    0xE3: 'Path cut by Kaeli (Axe)',

    0xF0: 'Figure for HP',

    # Engine & Poses
    0xF2: 'Alternate monster graphics gate',

    0xF5: 'Player pose flag - set player looking north(up)',
    0xF6: 'Player pose flag - set player looking ...',

    0xFB: 'Prompt choice boolean (0=Okay, 1=Sorry)',

    0xFD: 'Script scratchpad boolean',
}


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
