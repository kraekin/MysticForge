"""Operand families from the USA 1.0 $009E0E/$009E6E interpreter.

This describes instructions, not an event VM. Runtime operands are displayed
symbolically. No branch is selected and no native routine is executed.
"""
from dataclasses import dataclass
from .rom import pc,read,u16
from .event_context import known_bytes

@dataclass
class Command:
    size:int
    description:str
    edges:tuple=()
    stop:bool=False
    complete:bool=True
    text:str|None=None

# Format characters: b = byte, w = word, l = long address/value.
FIXED={
    0x00:('', 'Upload pending dialogue graphics'),
    0x01:('w','Wait for input · button mask'),
    0x1d:('wb','Push engine memory onto dialogue stack · source, byte count'),
    0x1e:('wb','Pop dialogue stack into engine memory · destination, byte count'),
    0x20:('', 'Move text cursor up one row'),0x21:('', 'Move text cursor down one row'),
    0x22:('', 'Move text cursor left one cell'),
    0x25:('', 'Copy memory using current source, destination and length'),
    0x27:('b','Write byte through working pointer · value'),
    0x29:('w','Write word through working pointer · value'),
    0x2b:('l','Write 24-bit value through working pointer · value'),
    0x2c:('w','Copy byte through working pointer to engine memory · destination'),
    0x2d:('w','Copy word through working pointer to engine memory · destination'),
    0x2e:('w','Copy three bytes through working pointer to engine memory · destination'),
    0x2f:('', 'Center dialogue window'),0x31:('', 'Clear entire dialogue tile buffer'),
    0x32:('', 'Clear dialogue window region'),
    0x35:('b','Prepare dialogue graphics rows · count'),
    0x37:('', 'Negate working value'),
    0x3a:('w','Store working 24-bit value in engine memory · destination'),
    0x3b:('b','Set working value · byte'),0x3c:('w','Set working value · word'),
    0x3d:('l','Set working value · 24-bit value'),
    0x40:('w','Load 24-bit working value from engine memory · address'),
    0x6b:('b','Shift working value right · count'),0x6c:('b','Shift working value left · count'),
    0x6d:('', 'Convert working number to decimal text buffer'),
    0x6e:('wb','Count glyphs in engine memory · address, byte count'),
    0x6f:('b','Mirror text cells horizontally · cell count'),
    0x72:('b','Set current-context bit · index'),0x73:('b','Clear current-context bit · index'),
    0x75:('b','Draw literal glyph · glyph code'),0x76:('', 'Fill memory using current engine parameters'),
    0x77:('', 'Count set bits in working word'),
    0x7e:('', 'Increment working value'),0x7f:('', 'Decrement working value'),
    0x83:('w','Increment byte in engine memory · address'),0x84:('w','Decrement byte in engine memory · address'),
    0x88:('w','Increment word in engine memory · address'),0x89:('w','Decrement word in engine memory · address'),
    0x8a:('', 'Draw current small portrait tiles'),0x8b:('', 'Extend dialogue upload range start'),
    0x8c:('', 'Extend dialogue upload range end'),0x8d:('', 'Wait for dialogue engine synchronization'),
    0xce:('w','Shift working value right · count from memory byte'),
    0xcf:('w','Shift working value left · count from memory byte'),
    0xd0:('', 'Find highest set bit in working word (zero has no terminating bit)'),
    0xd1:('b','Set text palette bits · palette mask'),
    0xd2:('b','Read indexed game flag into working value · index'),
    0xd3:('', 'Draw working word as a literal tile'),
    0xd4:('', 'Count glyphs at working pointer using current text length'),
    0xd5:('b','Center and display runtime character name · parameter'),
    0xd6:('', 'Set game flag indexed by working value'),0xd7:('', 'Clear game flag indexed by working value'),
    0xd8:('', 'Set current-context bit indexed by working value'),
    0xd9:('', 'Clear current-context bit indexed by working value'),
    0xda:('b','Generate bounded random value · bound'),
    0xdd:('', 'Draw alternate small portrait tiles'),
    0xde:('b','Look up engine character pointer · identifier'),
    0xdf:('', 'Look up engine character pointer using working value'),
    0xe5:('', 'Build dialogue graphics rows using current vertical parameters'),
    0xe9:('b','Count glyphs at working pointer · byte count'),
    0xeb:('', 'Refresh graphics for current engine mode'),
    0xec:('wbb','Fill engine memory · address, byte value, length counter'),
    0xed:('l','Load byte from long memory address'),
    0xee:('l','Load word from long memory address'),
    0xef:('l','Load 24-bit value from long memory address'),
    0xf0:('lb','Write byte to long memory · address, value'),
    0xf1:('lw','Write word to long memory · address, value'),
    0xf2:('ll','Write 24-bit value to long memory · address, value'),
    0xf3:('llw','Copy memory · source, destination, byte count'),
    0xf4:('wb','Load byte through stored pointer · pointer address, offset'),
    0xf5:('wb','Load word through stored pointer · pointer address, offset'),
    0xf6:('wb','Load 24-bit value through stored pointer · pointer address, offset'),
    0xf7:('', 'Restore party HP and clear incapacitated state'),
    0xf9:('bb','Set dialogue vertical parameters · first row, row count'),
}

# All six operators occur in the same order in each native family.
RELATIONS=('>','>=','<','<=','==','!=')
COMPARISONS={}
for first,kind,is_call in ((0x04,'b',False),(0xb6,'w',False),(0xc2,'l',False),
                           (0x92,'mb',False),(0x9e,'mw',False),(0xaa,'ml',False),
                           (0x78,'b',True),(0xbc,'w',True),(0xc8,'l',True),
                           (0x98,'mb',True),(0xa4,'mw',True),(0xb0,'ml',True)):
    for index,relation in enumerate(RELATIONS):
        # Primary $0B replaces the fifth member of the immediate-byte family.
        if first==4 and index==4:continue
        COMPARISONS[first+index]=(kind,relation,is_call)

MATH={}
for first,name,widths in ((0x42,'Add',('w','l','mb','mw','ml')),
                          (0x47,'Subtract',('b','w','l','mb','mw','ml')),
                          (0x4d,'Multiply',('b','w','mb','mw')),
                          (0x51,'Divide',('b','w','mb','mw')),
                          (0x55,'Remainder after division by',('b','w','mb','mw')),
                          (0x5a,'Bitwise AND',('w','l','mb','mw','ml')),
                          (0x5f,'Bitwise OR',('b','w','l','mb','mw','ml')),
                          (0x65,'Bitwise XOR',('b','w','l','mb','mw','ml'))):
    for i,kind in enumerate(widths):MATH[first+i]=(name,kind)

def operand(data,offset,kind):
    width=2 if kind.startswith('m') else {'b':1,'w':2,'l':3}[kind]
    value=int.from_bytes(read(data,offset,width),'little')
    return width,(f"{'byte' if kind=='mb' else 'word' if kind=='mw' else '24-bit value'} at engine memory ${value:04X}" if kind.startswith('m') else f'${value:0{width*2}X} ({value})')

def decode_command(rom,address,context):
    data=rom.data;o=pc(address);op=data[o];bank=address&0xff0000
    if op==6:return Command(1,'Conditional text spacing: line break or space (runtime text mode)')
    if op==0x0e:return Command(6,f'Write 24-bit value ${int.from_bytes(read(data,o+3,3),"little"):06X} to engine memory ${u16(data,o+1):04X}')
    if op==0x16:return Command(3,f'Draw literal tile word ${u16(data,o+1):04X}')
    if op==0x19:return Command(1,'Reset text cursor to configured position')
    if op==0x21:return Command(1,'Move text cursor right one cell')
    if op in (0x1c,0x22):
        target=0x030000|u16(data,pc(0x00a163 if op==0x1c else 0x00a157))
        return Command(1,'Close dialogue and return' if op==0x1c else 'Continue through shared engine event',(('jump',target),),True)
    if op!=5:return None
    sub=data[o+1]
    if sub==0xea and 0x9e in context:
        target=context[0x9e];length=data[o+2]
        try:read(data,pc(target),length)
        except ValueError:pass
        else:return Command(3,f'Display bounded text/event data at ROM ${target:06X} · {length} bytes',(('bounded',target),))
    if sub in COMPARISONS:
        kind,relation,call=COMPARISONS[sub];width,value=operand(data,o+2,kind);size=4+width
        target=bank|u16(data,o+2+width)
        words={'>':'is greater than','>=':'is at least','<':'is less than','<=':'is at most','==':'equals','!=':'does not equal'}
        return Command(size,f'{"Conditional call if" if call else "If"} working value {words[relation]} {value} (unsigned)',
                       (('call',target),) if call else (('yes',target),('no',address+size)),not call)
    if sub in MATH:
        name,kind=MATH[sub];width,value=operand(data,o+2,kind)
        return Command(2+width,f'{name} working value · operand {value}')
    if sub in (0x80,0x81,0x82,0x85,0x86,0x87):
        size=5 if sub<0x85 else 6;name=('AND','OR','XOR')[(sub-0x80)%5]
        return Command(size,f'Bitwise {name} {"byte" if size==5 else "word"} at engine memory ${u16(data,o+2):04X} with ${int.from_bytes(read(data,o+4,size-4),"little"):X}')
    if sub in FIXED:
        form,name=FIXED[sub];size=2;values=[]
        for kind in form:
            width,value=operand(data,o+size,kind);size+=width;values.append(value)
        return Command(size,name+(': '+', '.join(values) if values else ''))
    if sub==2:
        return Command(5,'Go to event in another bank',(('jump',int.from_bytes(read(data,o+2,3),'little')),),True)
    if sub in (3,0x11,0x17,0x19):
        # Exact local dispatcher: highest-set-bit -> *3 -> ROM pointer table.
        # These are known table candidates, not a claim that arbitrary runtime
        # inputs are in range. The zero input also has no terminating bit.
        prefix=bytes.fromhex('05d11805d0054d0305436b9f03052e9e00')
        if sub==0x11 and address==0x03b7f0 and data[o-len(prefix):o]==prefix:
            pointers=[int.from_bytes(read(data,pc(0x039f6b)+i*3,3),'little') for i in range(8)]
            if pointers==[0x03d3f1,0x03d3f8,0x03d3fd,0x03d412,0x03d40c,0x03d403,0x03d3e9,0x03d3e3]:
                return Command(2,'Call bit-selected handler · 8 verified table candidates; runtime selector and out-of-range behavior unresolved',tuple(('call',p) for p in pointers),False,False)
        target=context.get(0x9e)
        if target is not None and sub!=0x19:
            try:read(data,pc(target),1)
            except ValueError:pass
            else:
                if sub==0x17:return Command(2,f'Call native assembly ${target:06X} · pointer proven by preceding commands')
                return Command(2,f'{"Jump to" if sub==3 else "Call"} event ${target:06X} · pointer proven by preceding commands',(('jump' if sub==3 else 'call',target),),sub==3)
        return Command(2,{3:'Jump through runtime working pointer',0x11:'Call event through runtime working pointer',0x17:'Call native assembly through runtime working pointer',0x19:'Display bounded text/event data through runtime pointer and length'}[sub]+' · unresolved runtime target',(),sub==3,False)
    if sub==0x0e:return Command(4,'Call event with saved dialogue state',(('call',bank|u16(data,o+2)),))
    if sub in (0x12,0x13,0x14,0x15,0x90,0x91,0x8e,0x8f):
        indexed=sub in (0x90,0x91,0x8e,0x8f);size=4 if indexed else 5
        clear=sub in (0x13,0x15,0x91,0x8f);call=sub not in (0x8e,0x8f)
        target=bank|u16(data,o+size-2)
        scope='game flag' if sub in (0x12,0x13) else 'current-context bit'
        flag='indexed by working value' if indexed else f'${data[o+2]:02X}'
        return Command(size,f'{"Conditional call if" if call else "If"} {scope} {flag} is {"clear" if clear else "set"}',(('call',target),) if call else (('yes',target),('no',address+size)),not call)
    if sub==0x18:
        target=u16(data,o+2);length=data[o+4]
        # Native handler zeroes the bank byte; low addresses are RAM, not ROM.
        if target<0x8000:
            payload=known_bytes(context,target,length)
            if payload is not None and all(b>=0x80 for b in payload):
                from .events import text_fragment
                text=text_fragment(payload)
                return Command(5,f'Generated text at RAM ${target:04X} · {length} bytes proven by preceding writes',text=text)
            return Command(5,f'Execute {length} bytes at RAM ${target:04X} · unresolved runtime contents',(),False,False)
        return Command(5,f'Execute {length} bytes at bank-$00 address ${target:04X}',(('bounded',target),))
    if sub in (0xdb,0xdc):
        count=data[o+2];size=3+count*2
        edges=tuple((f'case {i}',bank|u16(data,o+3+i*2)) for i in range(count))
        if sub==0xdc:edges=tuple(('call',target) for _,target in edges)
        else:edges+=(('out of range',address+size),)
        return Command(size,f'{"Call" if sub==0xdc else "Branch"} using working value · {count} table entries',edges,sub==0xdb)
    if sub==0x30:
        return Command(2,'Repeat following instruction using runtime text-repeat count (body shown once)')
    if sub==0x36:
        count=context.get(0x2b)
        if count is None:return Command(2,'Dialogue row-pattern data · length depends on runtime window height; continuation unresolved',(),True,False)
        count=count or 65536
        payload=read(data,o+2,count)
        return Command(2+count,f'Dialogue row pattern · {count} rows: '+payload.hex(' ').upper())
    return None

def working_value(rom,raw,current):
    """Constant propagation for straight-line operands only, never execution."""
    op=raw[0]
    if op in (0x0c,0x0d,0x0e,0x0f,0x10,0x11,0x12,0x1d):return None
    if op in (0x13,0x14):
        if current is None:return None
        return (current+raw[1])&0xffffffff if op==0x13 else current&raw[1]
    if op!=5:return current
    sub=raw[1]
    if sub in (0x3b,0x3c,0x3d):return int.from_bytes(raw[2:],'little')
    if sub in (0xed,0xee,0xef):
        try:return int.from_bytes(read(rom.data,pc(int.from_bytes(raw[2:],'little')),sub-0xed+1),'little')
        except ValueError:return None
    if sub in MATH:
        name,kind=MATH[sub]
        if current is None or kind.startswith('m'):return None
        value=int.from_bytes(raw[2:],'little')
        if name=='Add':return (current+value)&0xffffffff
        if name=='Subtract':return (current-value)&0xffffffff
        if name=='Multiply':return (current&0xffff)*value
        if name=='Divide':return current//value if value else None
        if name.startswith('Remainder'):return current%value if value else None
        return {'Bitwise AND':current&value,'Bitwise OR':current|value,'Bitwise XOR':current^value}[name]
    if sub in (0x6b,0x6c):
        if current is None or not raw[2]:return None
        return current>>raw[2] if sub==0x6b else (current<<raw[2])&0xffffffff
    # Output/copy/configuration commands preserve the working register.
    safe={0,1,0x1d,0x20,0x21,0x22,0x2f,0x31,0x32,0x35,0x36,0x6d,
          0x75,0x8a,0x8b,0x8c,0x8d,0xd1,0xd3,0xdd,0xe1,0xe2,0xe3,0xe5,0xeb,0xf9}
    return current if sub in safe else None
