"""Verified fixed database spans and lossless field edits for USA v1.0."""
from dataclasses import dataclass
from .rom import pc,FormatError
from .events import text_fragment

TABLES={
 'monster_stat':(0x02C275,83,14),'monster_level':(0x02C17C,83,3),
 'monster_attacks':(0x02C6FF,83,9),'monster_name':(0x0CCBA0,81,16),
 'attack':(0x02BC78,169,7),'attack_name':(0x0CC420,156,12),
 'weapon':(0x02BC00,15,8),'armor':(0x02C127,17,5),
 'character':(0x0CD0B0,9,80),'battlefield':(0x07EFA1,20,2)}

WEAPONS=('Steel Sword','Knight Sword','Excalibur','Axe','Battle Axe',"Giant’s Axe",'Cat Claw','Charm Claw','Dragon Claw','Bomb','Jumbo Bomb','Mega Grenade','Morning Star','Bow of Grace','Ninja Star')
ARMORS=('Steel Helm','Moon Helm','Apollo Helm','Steel Armor','Noble Armor',"Gaia’s Armor",'Replica Armor','Mystic Robes','Flame Armor','Black Robe','Steel Shield','Venus Shield','Aegis Shield','Ether Shield','Charm','Magic Ring','Cupid Locket')
STATUS=('Silence','Blind','Poison','Confusion','Sleep','Paralysis','Stone','Doom')
ELEMENTS=('Projectile','Bomb','Axe','Zombie','Air','Fire','Water','Earth')
SPELLS=('Exit','Cure','Heal','Life','Quake','Blizzard','Fire','Aero','Thunder','White','Meteor','Flare')


def name(raw):return text_fragment(raw.split(b'\x03')[0]).replace('[06]',' ')

def encode_name(text,size):
    mapping={text_fragment(bytes([i])):i for i in range(0x90,0xde) if len(text_fragment(bytes([i])))==1}
    mapping[' ']=0xff
    if len(text)>size:raise FormatError(f'Name exceeds {size} encoded characters')
    if any(c not in mapping for c in text):raise FormatError('Name contains a character unsupported by the game font')
    return bytes(mapping[c] for c in text)+b'\x03'*(size-len(text))

@dataclass(frozen=True)
class Field:
    label:str
    kind:str
    offset:int
    size:int=1
    mask:int|None=None
    choices:tuple=()
    readonly:bool=False
    text:bool=False
    group:str='General'
    def read(self,raw):
        data=raw[self.offset:self.offset+self.size]
        if self.text:return name(data)
        value=int.from_bytes(data,'little')
        return value if self.mask is None else (value&self.mask)//(self.mask&-self.mask)
    def encode(self,raw,value):
        data=bytearray(raw)
        if self.text:part=encode_name(value,self.size)
        else:
            old=int.from_bytes(raw[self.offset:self.offset+self.size],'little')
            mask=self.mask if self.mask is not None else (1<<(8*self.size))-1
            shift=mask&-mask
            if type(value) is not int or value<0 or value*shift&~mask:raise FormatError('Field value is outside its stored range')
            part=((old&~mask)|(value*shift)).to_bytes(self.size,'little')
        data[self.offset:self.offset+self.size]=part
        return bytes(data)

def flags(kind,offset,labels,group):
    return [Field(label,kind,offset,mask=1<<i,choices=((0,'No'),(1,'Yes')),group=group) for i,label in enumerate(labels)]

def fields(category,index):
    f=[]
    if category=='Monsters':
        if index<81:f.append(Field('Name','monster_name',0,16,text=True))
        f+=[Field('HP','monster_stat',0,2)]+[Field(label,'monster_stat',i+2) for i,label in enumerate(('Attack','Defense','Speed','Magic'))]
        f+=[Field(label,'monster_stat',i+8) for i,label in enumerate(('Magic defense','Magic evade','Accuracy','Evade'))]
        f+=[Field(label,'monster_level',i) for i,label in enumerate(('Level','XP multiplier (stored)','Gold multiplier (stored)'))]
        f+=flags('monster_stat',6,ELEMENTS,'Element resistances')+flags('monster_stat',7,STATUS,'Status resistances')+flags('monster_stat',12,ELEMENTS,'Element weaknesses')
        f.append(Field('Undead','monster_stat',13,mask=4,choices=((0,'No'),(1,'Yes')),group='Target properties'))
        f.append(Field('Other target flags (raw)','monster_stat',13,readonly=True,group='Technical data'))
        f.append(Field('Attack pattern','monster_attacks',0,mask=15,choices=tuple((i,f'Pattern {i}') for i in range(16)),group='Attack slots'))
        f += [Field(f'Attack slot {i}','monster_attacks',i,choices=tuple((v,f'Action ${v:02X}') for v in range(169))+((255,'None / unused'),),group='Attack slots') for i in range(1,7)]
        f += [Field(label,'monster_attacks',i,readonly=True,group='Technical data') for i,label in ((0,'Pattern / extra flags (raw)'),(7,'Conditional Heal action (raw)'),(8,'Conditional Cure action (raw)'))]
    elif category=='Attacks & spells':
        if index<156:f.append(Field('Name','attack_name',0,12,text=True))
        f += [Field('Base power','attack',2),Field('Effect handler','attack',3,mask=63,choices=tuple((i,{11:'Exit',12:'Life',13:'Heal',14:'Cure'}.get(i,f'Effect ${i:02X}')) for i in range(32))),Field('Handler / calculation bits (raw)','attack',3,readonly=True,group='Technical data'),Field('Secondary calculation byte (raw)','attack',4,readonly=True,group='Technical data'),Field('Targeting byte (raw)','attack',5,readonly=True,group='Technical data'),Field('Animation / message byte (raw)','attack',6,readonly=True,group='Technical data')]
        f+=flags('attack',0,ELEMENTS,'Elements')+flags('attack',1,STATUS,'Statuses')
    elif category=='Weapons':
        f=[Field('Power','weapon',2)]+flags('weapon',0,ELEMENTS,'Elements')+flags('weapon',1,STATUS,'Statuses')
        f += [Field(f'Effect byte {i:02X} (raw)','weapon',i,readonly=True,group='Technical data') for i in range(3,8)]
    elif category=='Armor':
        f=[Field('Defense','armor',3),Field('Boost flags (raw)','armor',2,readonly=True,group='Technical data'),Field('Evade / extra byte (raw)','armor',4,readonly=True,group='Technical data')]
        f+=flags('armor',0,ELEMENTS,'Element resistances')+flags('armor',1,STATUS,'Status resistances')
    elif category=='Character templates':
        f=[Field('Name (first 8 displayed characters)','character',0,8,text=True),Field('Level','character',16),Field('Experience','character',17,3),Field('Current HP','character',20,2),Field('Maximum HP','character',22,2)]
        f += [Field(label,'character',24+i) for i,label in enumerate(('White MP','Black MP','Wizard MP','Maximum white MP','Maximum black MP','Maximum wizard MP'))]
        for base,group in ((0x22,'Effective stats'),(0x26,'Base stats'),(0x2a,'Bonus stats')):f += [Field(label,'character',base+i,group=group) for i,label in enumerate(('Attack','Defense','Speed','Magic'))]
        f += [Field('Ammo','character',0x30),Field('Equipped weapon','character',0x31,choices=tuple((32+i,label) for i,label in enumerate(WEAPONS)))]
        for base,labels,group in ((0x32,WEAPONS,'Owned weapons'),(0x35,ARMORS,'Owned armor')):
            f += [Field(label,'character',base+i//8,mask=0x80>>(i%8),choices=((0,'No'),(1,'Yes')),group=group) for i,label in enumerate(labels)]
        f += [Field(label,'character',0x38+i//8,mask=0x80>>(i%8),choices=((0,'No'),(1,'Yes')),group='Known spells') for i,label in enumerate(SPELLS)]
        f += [Field('Accuracy','character',0x40),Field('Magic evade','character',0x41),Field('Partner ID (raw)','character',0x20,readonly=True,group='Technical data')]
    elif category=='Battlefield rewards':
        f=[Field('Reward encoding (hex)','battlefield',0,2,readonly=True),Field('Payload (raw units)','battlefield',0,2,mask=0x3fff),Field('Reward type','battlefield',0,2,mask=0xc000,choices=((0,'Gold'),(1,'Item / equipment / spell'),(2,'Experience')),group='General')]
    return f

CATEGORIES={'Monsters':83,'Attacks & spells':169,'Weapons':15,'Armor':17,'Character templates':9,'Battlefield rewards':20}

def title(project,category,index):
    if category=='Monsters':return name(project.fixed('monster_name',index)) if index<81 else f'Extra monster statistics ${index:02X}'
    if category=='Attacks & spells':return name(project.fixed('attack_name',index)) if index<156 else ('Special action' if index==156 else ('Exit','Cure','Heal','Life','Quake','Blizzard','Fire','Aero','Thunder','White','Meteor','Flare')[index-157])
    if category=='Weapons':return WEAPONS[index]
    if category=='Armor':return ARMORS[index]
    if category=='Character templates':return name(project.fixed('character',index)[:8])+f' · template {index}'
    return f'Battlefield {index+1}'

def proposed_changes(project,index,original,updates):
    result=dict(original)
    for field,value in updates:
        if field.readonly:raise FormatError('This field is read-only')
        result[field.kind]=field.encode(result[field.kind],value)
    changes={}
    for kind,raw in result.items():
        if project.fixed(kind,index)!=original[kind]:raise FormatError('This record changed since it was opened. Reload before applying.')
        changes.update({(kind,index,i):(a,b) for i,(a,b) in enumerate(zip(original[kind],raw)) if a!=b})
    return changes


def validate_record(project,kind,index,raw):
    if kind=='battlefield':
        value=int.from_bytes(raw,'little');reward_type=value>>14;payload=value&0x3fff
        if reward_type==3:raise FormatError('Both reward type bits cannot be enabled')
        if reward_type==1 and payload>63:raise FormatError('Item reward must be an item ID from $00 to $3F')
    if kind=='attack' and raw[3]&63>31 and raw[3]!=project.original((kind,index,3)):
        raise FormatError('Unknown effect handlers can be preserved but cannot be newly assigned')
    if kind=='monster_attacks':
        for i,value in enumerate(raw[1:7],1):
            if value>168 and value!=255 and value!=project.original((kind,index,i)):
                raise FormatError('Unknown attack IDs can be preserved but cannot be newly assigned')
