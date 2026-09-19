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
    0x16: 'Fireburg locked house in pit checked with Reuben (triggers Tristam)',
    0x17: 'Life Temple entrance cutscene completed (Spring of Life dried up)',

    0x1C: 'Fireburg locked house unlocked (opened with Multi-Key)',
    0x1D: 'Giant Tree set',
    0x1E: 'Minotaur defeated',
    0x1F: 'Kaeli cured with Elixir(unlocks focus tower route)',

    0x20: 'Focus Tower 2F movable pillar unmoved (starting position)',
    0x21: 'Focus Tower 2F movable pillar moved into slot (bridge formed)',
    0x22: 'Hill of Destiny collapsed',
    0x23: 'Sand Coin used at Sand Temple',
    0x24: 'Squidite present in Wintry Cave',
    0x25: 'Snow Crab present in Falls Basin',
    0x26: 'Jinn present in Mine exterior (cleared on defeat)',

    0x2C: 'Focus Tower Earth Door open',
    0x2D: 'Focus Tower Water Door open',
    0x2E: 'Focus Tower Fire Door open',
    0x2F: 'Focus Tower Wind Door open',

    0x30: 'Focus Tower Earth Door closed',
    0x31: 'Focus Tower Water Door closed',
    0x32: 'Focus Tower Fire Door closed',
    0x33: 'Focus Tower Wind Door closed',

    # Boulders & Terrain Obstacles
    0x34: 'Level Forest boulder obstacle active',
    0x35: 'Wintry Cave collapsed',
    0x36: 'Fireburg boulder in blocking position',
    0x37: 'Arion rescued from Mine / returned home to Fireburg',


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

    0x50: "Ice Golem present in Ice Pyramid (hallway taunt encounter)",

    0x53: 'Multi-Key received from Tristam in Fireburg Hotel (cleared on receive)',

    0x5A: 'Tristam present in Sand Temple',
    0x5B: 'River Coin used',
    0x5C: 'Mine boulder destroyed (overworld route opened)',
    0x5D: 'Medusa defeated',
    0x5E: "Phoebe present in Aquaria house (post-Ice Golem)",
    0x5F: 'Reuben present in Fireburg house (cleared when Reuben joins party)',

    0x60: 'Reuben searching for father / Mega Grenade with Hero',
    0x61: 'Arion rescued from Mine',
    0x62: 'Kaeli at her home in Foresta',
    0x63: 'Enable Minotaur fight',
    0x64: 'Volcano erupted',
    0x65: 'Sun Coin used (Fire door opened)',

    0x6C: 'Mysterious Man present in forest',
    0x6D: 'Hide diseased tree in Level Forest',
    0x6E: 'Talk to Tristam',
    0x6F: 'Elixir given to Kaeli',

    0x70: 'Talk to Phoebe',
    0x71: 'Phoebe house intro cutscene watched',
    0x72: 'Aquaria Wakewater cutscene watched',
    0x73: 'Exit Fall Basin',
    0x74: 'Talk to Grenade Guy',

    0x7A: 'Prologue complete',
    0x7D: 'Kaeli sick in bed',

    # Active / Uncleared Battlefield Flags ($81–$94)
    0x81: 'Foresta South Battlefield active (uncleared)',
    0x82: 'Foresta West Battlefield active (uncleared)',
    0x83: 'Foresta East Battlefield active (uncleared)',
    0x84: 'Aquaria Battlefield 1 active (uncleared)',
    0x85: 'Aquaria Battlefield 2 active (uncleared)',
    0x86: 'Aquaria Battlefield 3 active (uncleared)',
    0x87: 'Wintry Battlefield 1 active (uncleared)',
    0x88: 'Wintry Battlefield 2 active (uncleared)',
    0x89: 'Pyramid Battlefield active (uncleared)',
    0x8A: 'Libra Battlefield 1 active (uncleared)',
    0x8B: 'Libra Battlefield 2 active (uncleared)',
    0x8C: 'Fireburg Battlefield 1 active (uncleared)',
    0x8D: 'Fireburg Battlefield 2 active (uncleared)',
    0x8E: 'Fireburg Battlefield 3 active (uncleared)',
    0x8F: 'Mine Battlefield 1 active (uncleared)',
    0x90: 'Mine Battlefield 2 active (uncleared)',
    0x91: 'Mine Battlefield 3 active (uncleared)',
    0x92: 'Volcano Battlefield active (uncleared)',
    0x93: 'Windia Battlefield 1 active (uncleared)',
    0x94: 'Windia Battlefield 2 active (uncleared)',

    # Cleared / Reward Claimed Battlefield Flags ($95–$A8)
    0x95: 'Foresta South Battlefield cleared (reward claimed)',
    0x96: 'Foresta West Battlefield cleared (reward claimed)',
    0x97: 'Foresta East Battlefield cleared (reward claimed)',
    0x98: 'Aquaria Battlefield 1 cleared (reward claimed)',
    0x99: 'Aquaria Battlefield 2 cleared (reward claimed)',
    0x9A: 'Aquaria Battlefield 3 cleared (reward claimed)',
    0x9B: 'Wintry Battlefield 1 cleared (reward claimed)',
    0x9C: 'Wintry Battlefield 2 cleared (reward claimed)',
    0x9D: 'Pyramid Battlefield cleared (reward claimed)',
    0x9E: 'Libra Battlefield 1 cleared (reward claimed)',
    0x9F: 'Libra Battlefield 2 cleared (reward claimed)',
    0xA0: 'Fireburg Battlefield 1 cleared (reward claimed)',
    0xA1: 'Fireburg Battlefield 2 cleared (reward claimed)',
    0xA2: 'Fireburg Battlefield 3 cleared (reward claimed)',
    0xA3: 'Mine Battlefield 1 cleared (reward claimed)',
    0xA4: 'Mine Battlefield 2 cleared (reward claimed)',
    0xA5: 'Mine Battlefield 3 cleared (reward claimed)',
    0xA6: 'Volcano Battlefield cleared (reward claimed)',
    0xA7: 'Windia Battlefield 1 cleared (reward claimed)',
    0xA8: 'Windia Battlefield 2 cleared (reward claimed)',

    # Late-Game / Special Triggers
    0xAD: 'Venus Shield chest in Focus Tower unopened (cleared on collect)',
    0xB2: 'Libra Crest chest spawned in Wintry Cave',
    0xB3: 'Fall Basin chest spawned',

    0xC6: "Mysterious Man present in Focus Tower subterranean cave",
    0xC7: 'Mysterious Man present in Sealed Temple Cave (cleared on talk)',
    0xC9: 'Tristam departs from Bone Dungeon (leaving party)',

    0xCB: 'Mysterious Man present in Focus Tower cave',

    0xCD: "Mysterious Man present in Focus Tower 2F",
    0xCE: 'Mysterious Man present in Life Temple',
    0xCF: 'Rainbow Road active',

    0xDB: 'Tristam present in Bone Dungeon (boss room)',
    0xDE: 'Fireburg locked house door barrier visible (cleared when unlocked)',
    0xDF: 'Mine boulder barrier visible (cleared on destruction)',

    0xE0: 'Squidite defeated',
    0xE1: 'Falls Basin entrance cutscene completed',
    0xE2: 'Ice Pyramid entrance cutscene completed (statue switch hint)',

    0xE3: 'Path cut by Kaeli (Axe)',

    0xF0: 'Figure for HP',

    # Engine & Poses
    0xF2: 'Alternate monster graphics gate',
    0xF3: 'Preserve scene state across map warp (cutscene transition flag)',
    0xF5: 'Player pose flag - set player looking north(up)',
    0xF6: 'Player pose flag - set player looking south(down)',
    0xF7: '',
    0xF8: '',
    0xF9: '',

    0xFA: 'Item dialogue "et" suffix flag',
    0xFB: 'Prompt choice boolean (0=Okay, 1=Sorry)',
    0xFC: 'Item dialogue plural suffix flag (append "s")',
    0xFD: 'Script scratchpad boolean',
    0xFE: 'Cutscene animation in progress (transient boulder/travel animation flag)',

}


KNOWN_NAMES = {key:value for key,value in (BEHAVIOR_NAMES | NAMES).items() if value.strip()}

EVIDENCE='research/RESTORATION_STATES.md — vanilla restoration flags and area action lists'

def flag_label(value):
    if NAMES.get(value):return f'${value:02X} — {NAMES[value]}'
    if BEHAVIOR_NAMES.get(value):return f'${value:02X} — {BEHAVIOR_NAMES[value]} (verified use)'
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
