"""Bounded read-only event decoding. Unknown lengths terminate a path."""
from dataclasses import dataclass
from .rom import pc,read,u16
from .event_commands import decode_command,working_value
from .field_actions import field_action
from .event_context import update_memory,known_bytes,interaction_note
from .event_flags import name_flags

@dataclass(frozen=True)
class Instruction:
    address:int
    raw:bytes
    description:str
    edges:tuple=()
    complete:bool=True
    text:str|None=None

def status(row):
    if row.complete:return 'decoded'
    text=row.description.lower()
    if 'inspection limit' in text:return 'limit'
    if 'runtime' in text:return 'runtime'
    if 'stops here' in text:return 'unsupported'
    return 'invalid'

def text_fragment(raw):
    # The historical compression-aware table agrees with local dialogue and
    # name records; the generated simple tables mislabel punctuation.
    punctuation={0xce:'!',0xcf:'?',0xd0:',',0xd1:"'",0xd2:'.',0xd3:'“',0xd4:'”',0xd5:'.”',0xd6:';',0xd7:':',0xd8:'…',0xd9:'/',0xda:'-',0xdb:'&',0xdc:'▶',0xdd:'%',0xff:' '}
    return ''.join(chr(48+b-0x90) if 0x90<=b<=0x99 else chr(65+b-0x9a) if 0x9a<=b<=0xb3 else chr(97+b-0xb4) if 0xb4<=b<=0xcd else punctuation.get(b,f'[{b:02X}]') for b in raw)

def inline_name(rom,opcode,index):
    # Exact helper bodies multiply the supplied index by these strides,
    # add these ROM bases, and output a bounded name span via $05EA.
    profiles={0x1f:(0x0CBED0,16,16,37),0x1e:(0x0CC120,12,12,224),0x1d:(0x0CD0B0,80,8,9),0x20:(0x0CCBA0,16,16,81)}
    if opcode not in profiles:return None
    base,stride,length,count=profiles[opcode]
    if not 0<=index<count:return None
    return text_fragment(read(rom.data,pc(base)+index*stride,length).replace(b'\x03',b'')).strip()

def fragments(rom):
    cursor=pc(0x03BA86);result=[]
    for _ in range(79):
        length=rom.data[cursor];address=0x038000+(cursor+1-pc(0x038000))
        result.append((address,length));cursor+=length+1
    return result

def decode(rom,entry,limit=256,follow_calls=True,extent=None):
    dictionary=fragments(rom);ends={a:a+n for a,n in dictionary}
    pending=[(entry,entry+extent if extent is not None else ends.get(entry),())];seen=set();result=[]
    while pending and len(result)<limit:
        address,bound,settings=pending.pop(0);context=dict(settings)
        if (address,bound,settings) in seen or address==bound:continue
        seen.add((address,bound,settings))
        try:
            offset=pc(address);op=rom.data[offset]
            size=1;description="";targets=[];stop=False;known=True
            command=decode_command(rom,address,context)
            if command is not None:
                size=command.size;description=command.description;targets=list(command.edges);stop=command.stop;known=command.complete
            elif op==0:description="End / return from event";stop=True
            elif op==4:description="No operation"
            elif op==0x17:
                size=2;description=f'Clear interpreter control bit ${rom.data[offset+1]:02X}'
            elif op==0x18:description='Draw dialogue window using current style'
            elif op==9:
                size=4;target=int.from_bytes(read(rom.data,offset+1,3),'little')
                description=f'Call native engine routine ${target:06X} (assembly, not event bytecode)'
            elif op in (0x0f,0x10,0x11,0x12):
                size=3
                description=(f"Load {'byte' if op==0x0f else 'word'} from engine memory ${u16(rom.data,offset+1):04X} into working value" if op<0x11 else f"Store working {'byte' if op==0x11 else 'word'} into engine memory ${u16(rom.data,offset+1):04X}")
            elif op==0x14:
                size=2;description=f'Mask working value with ${rom.data[offset+1]:02X}'
            elif op==0x13:
                size=2;description=f'Add {rom.data[offset+1]} to working value'
            elif op in (1,2,3):description={1:'New line',2:'Blank line',3:'Text spacing'}[op]
            elif op==0x0b or (op==5 and rom.data[offset+1]==9):
                argument=offset+(1 if op==0x0b else 2);size=4 if op==0x0b else 5
                comparison='equals' if op==0x0b else 'does not equal'
                description=f'If working value {comparison} {rom.data[argument]} (runtime-dependent)'
                targets=[('yes',(address&0xff0000)|u16(rom.data,argument+1)),('no',address+size)];stop=True
            elif op==5 and rom.data[offset+1] in (0xa2,0xa3):
                size=6;comparison='equals' if rom.data[offset+1]==0xa2 else 'does not equal'
                description=f'If working value {comparison} word at engine memory ${u16(rom.data,offset+2):04X} (runtime-dependent)'
                targets=[('yes',(address&0xff0000)|u16(rom.data,offset+4)),('no',address+size)];stop=True
            elif op==5 and rom.data[offset+1]==0xf9:
                size=4;description=f'Set dialogue vertical parameters: {rom.data[offset+2]}, {rom.data[offset+3]}'
            elif op==5 and rom.data[offset+1] in (0x2f,0x32,0x35,0x3d,0x40,0x60,0x6c,0xeb):
                sub=rom.data[offset+1];size={0x2f:2,0x32:2,0x35:3,0x3d:5,0x40:4,0x60:4,0x6c:3,0xeb:2}[sub]
                if sub==0x35:description=f'Prepare text graphics buffer · parameter ${rom.data[offset+2]:02X}'
                elif sub==0x3d:description=f"Set working pointer to ${int.from_bytes(read(rom.data,offset+2,3),'little'):06X}"
                elif sub==0x40:description=f'Load working pointer from engine memory ${u16(rom.data,offset+2):04X}'
                elif sub==0x60:description=f'Combine working value with mask ${u16(rom.data,offset+2):04X} (bitwise OR)'
                elif sub==0x6c:description=f'Shift working value left · count {rom.data[offset+2]}'+(' (zero underflows the engine counter)' if not rom.data[offset+2] else '')
                else:description={0x2f:'Center dialogue window',0x32:'Clear dialogue window region',0xeb:'Refresh graphics for current engine mode'}[sub]
            elif op==0x0a:
                size=3;description='Go to branch';targets=[('jump',(address&0xff0000)|u16(rom.data,offset+1))];stop=True
            elif op in (0x0c,0x0d):
                size=4 if op==0x0c else 5
                description=f"Write {'byte' if op==0x0c else 'word'} ${int.from_bytes(read(rom.data,offset+3,size-3),'little'):X} to engine memory ${u16(rom.data,offset+1):04X}"
            elif op in (0x15,0x24,0x25,0x26,0x27,0x28,0x29):
                size={0x15:3,0x24:5,0x25:2,0x26:4,0x27:2,0x28:2,0x29:2}[op]
                description={0x15:'Set text position',0x24:'Set text window parameters',0x25:'Set text attribute',0x26:'Set text pointer parameters',0x27:'Set text display parameter',0x28:'Set text character attribute',0x29:'Set interpreter control bit'}[op]+': '+read(rom.data,offset+1,size-1).hex(' ').upper()
            elif op in (0x1a,0x1b,0x1d,0x1e,0x1f,0x20):
                size=2
                operand={0x1a:0xA179,0x1b:0xA18F,0x1d:0xA14B,0x1e:0xA111,0x1f:0xA0D3,0x20:0xA0F2}[op]
                target=0x030000|u16(rom.data,pc(operand))
                description=f'Run interaction/dialogue helper with reference ${rom.data[offset+1]:02X}'
                name=inline_name(rom,op,rom.data[offset+1])
                if name is not None:description=f'Insert { {0x1f:"location",0x1e:"item",0x1d:"character-record",0x20:"enemy"}[op]} name: {name}'
                elif op in (0x1a,0x1b):description=f'Open dialogue message · window {"A" if op==0x1a else "B"}, reference ${rom.data[offset+1]:02X}'
                targets=[('call',target)]
            elif op==0x2f:description="Select item-flag context"
            elif op in (0x23,0x2b):
                size=2;description=f"{'Set' if op==0x23 else 'Clear'} game flag ${rom.data[offset+1]:02X}"
            elif op==0x2d:
                size=3;description=f"Select flag context ${u16(rom.data,offset+1):04X}"
            elif op==0x2e:
                size=4;flag=rom.data[offset+1];target=(address&0xff0000)|u16(rom.data,offset+2)
                description=f"If game flag ${flag:02X} is set";targets=[("set",target),("clear",address+size)];stop=True
            elif op==5 and rom.data[offset+1]==0x0b:
                size=5;flag=rom.data[offset+2];target=(address&0xff0000)|u16(rom.data,offset+3)
                description=f"If game flag ${flag:02X} is clear";targets=[("clear",target),("set",address+size)];stop=True
            elif op==5 and rom.data[offset+1] in (0x0c,0x0d):
                sub=rom.data[offset+1];size=5;bit=rom.data[offset+2]
                description=f"If current-context bit ${bit:02X} is {'set' if sub==0x0c else 'clear'} (context-dependent)"
                targets=[('yes',(address&0xff0000)|u16(rom.data,offset+3)),('no',address+size)];stop=True
            elif op==5 and rom.data[offset+1] in (0xfc,0xfd,0xfe,0xff):
                sub=rom.data[offset+1];size=5;bit=rom.data[offset+2]
                target=(address&0xff0000)|u16(rom.data,offset+3)
                if sub<0xfe:
                    description=f"If interpreter control bit ${bit:02X} is {'set' if sub==0xfc else 'clear'}"
                    targets=[('yes',target),('no',address+size)];stop=True
                else:
                    description=f"Conditional call when interpreter control bit ${bit:02X} is {'set' if sub==0xfe else 'clear'}"
                    targets=[('call',target)]
            elif op==5 and rom.data[offset+1]==0x4d:
                size=3;description=f'Multiply working value by {rom.data[offset+2]}'
            elif op==5 and rom.data[offset+1] in (0x24,0xea,0xe2,0xe3,0xe1,0xe4,0xe6,0xe7,0xe8):
                sub=rom.data[offset+1]
                size={0x24:7,0xea:3,0xe2:2,0xe3:2,0xe1:3,0xe4:4,0xe6:3,0xe7:2,0xe8:2}[sub]
                if sub==0x24:description=f'Copy {rom.data[offset+6]} bytes: ${u16(rom.data,offset+2):04X} → ${u16(rom.data,offset+4):04X}'
                elif sub==0xea:description=f'Execute {rom.data[offset+2]} bytes from runtime script pointer (target depends on working value)';known=False
                elif sub==0xe1:description=f'Wait {rom.data[offset+2]} frames' if rom.data[offset+2] else 'Wait frames · zero underflows the engine counter'
                elif sub==0xe4:description=f'Start battle · encounter ${rom.data[offset+2]:02X}, battle parameter ${rom.data[offset+3]:02X}'
                elif sub==0xe6:description=f'Load companion record ${rom.data[offset+2]:02X}'
                else:description={0xe2:'Wait for engine timing/input service',0xe3:'Wait one frame',0xe7:'Restore party HP/MP',0xe8:'Restore party HP/MP and clear status'}[sub]
            elif op==5 and rom.data[offset+1] in (0x1d,0x2c,0x42,0x43):
                sub=rom.data[offset+1];size={0x1d:5,0x2c:4,0x42:4,0x43:5}[sub]
                description={0x1d:'Copy data into text buffer',0x2c:'Read indirect byte into engine memory',0x42:'Add word to working value',0x43:'Add 24-bit value to working pointer'}[sub]+': '+read(rom.data,offset+2,size-2).hex(' ').upper()
            elif op==8:
                size=3;target=(address&0xff0000)|u16(rom.data,offset+1)
                description="Call event in current bank";targets=[("call",target)]
            elif op==7:
                size=4;target=int.from_bytes(read(rom.data,offset+1,3),'little')
                description="Call event (bank and address)";targets=[("call",target)]
            elif op==0x2a:
                actions=[];size=1
                while True:
                    if size>255 or (address&0xffff)+size+2>0x10000:raise ValueError('unterminated action sequence')
                    value=u16(rom.data,offset+size);size+=2
                    if value==0xffff:break
                    if value>=0x8000:
                        actions.append(f'call ${value:04X}');targets.append(('call',0x030000|value))
                    else:actions.append(field_action(value>>8,value&255))
                description='Field action sequence: '+', '.join(actions)
            elif op==0x2c:
                size=3;value=u16(rom.data,offset+1)
                if value>=0x8000:description="Call bank-$03 event";targets=[("call",0x030000|value)]
                else:description=field_action(value>>8,value&255)
            elif 0x30<=op<0x80:
                if op-0x30>=len(dictionary):
                    description='Reference $7F is outside the stored fragment table';stop=True;known=False
                else:
                    target,length=dictionary[op-0x30];payload=read(rom.data,pc(target),length)
                    description=f"Shared text/event fragment ${op-0x30:02X}"
                    if all(b>=0x80 for b in payload):description+=f': “{text_fragment(payload)}”'
                    targets=[('fragment',target)]
            elif op>=0x80:
                description="Text character data (preserved; not interpreted)"
                while size<32 and offset+size<len(rom.data) and rom.data[offset+size]>=0x80 and (address&0xffff)+size<0x10000 and (bound is None or address+size<bound):size+=1
                description='Text: “'+text_fragment(read(rom.data,offset,size))+'”'
            else:
                description=f"Unsupported {'text/reference' if op>=0x30 else 'command'} ${op:02X} — decoding stops here"
                if op==5:description=f"Extended command $05/${rom.data[offset+1]:02X} — decoding stops here";size=2
                stop=True;known=False
            if (address&0xffff)+size>0x10000:raise ValueError("instruction crosses bank boundary")
            if bound is not None and address+size>bound:raise ValueError('instruction crosses fragment boundary')
            raw=read(rom.data,offset,size)
            if not stop and address+size!=bound:targets.append(("next",address+size))
            valid=[]
            for label,target in targets:
                try:read(rom.data,pc(target),1);valid.append((label,target))
                except ValueError:description+=f"; invalid {label} target ${target:06X}";known=False
            note=interaction_note(raw,context.get(0x9e))
            if note:description+=' · '+note
            result.append(Instruction(address,raw,name_flags(description),tuple(valid),known,command.text if command is not None else None))
            previous_working=context.get(0x9e)
            working=working_value(rom,raw,context.get(0x9e))
            if raw[:2]==b'\x05\x40':
                payload=known_bytes(context,u16(raw,2),3)
                if payload is not None:working=int.from_bytes(payload,'little')
            if raw[:2]==b'\x05\x2e' and u16(raw,2)==0x9e and previous_working is not None:
                try:working=int.from_bytes(read(rom.data,pc(previous_working),3),'little')
                except ValueError:working=None
            update_memory(context,raw,previous_working)
            if working is None:context.pop(0x9e,None)
            else:context[0x9e]=working
            if op==0x24:context[0x2b]=raw[4]
            elif op in (0x0c,0x0d,0x0e):
                destination=u16(raw,1)
                for i,value in enumerate(raw[3:]):
                    if destination+i==0x2b:context[0x2b]=value
            elif op in (0x11,0x12) and u16(raw,1)<=0x2b<u16(raw,1)+size-1:context.pop(0x2b,None)
            for label,target in valid:
                if not follow_calls and label in ('call','fragment','bounded'):continue
                child_bound=(target+raw[-1]) if label=='bounded' else ends.get(target) if label in ('call','fragment') else bound
                # A callee can alter window configuration. Never guess its
                # returned state when following the caller's continuation.
                next_context=dict(context)
                if label=='next' and (op==9 or any(l in ('call','fragment','bounded') for l,_ in valid)):next_context={}
                if label not in ('next','call','fragment','bounded'):next_context.pop(0x9e,None)
                if label=='call' and op in (0x1d,0x1e,0x1f,0x20):next_context[0x9e]=raw[1]
                pending.append((target,child_bound,tuple(sorted(next_context.items()))))
        except (ValueError,IndexError):result.append(Instruction(address,b'',"Invalid or truncated event data",(),False))
    if pending:result.append(Instruction(pending[0][0],b'',f"Inspection limit ({limit} commands) reached",(),False))
    return result

def world_entry(rom,value):
    return 0x030000|u16(rom.data,pc(0x03BBD2)+value*2)

def npc_entry(rom,value):
    # $03D636..$03D72D holds 124 pointers. Higher IDs read script bytes,
    # not another verified entry. Some hidden/noninteractive objects use them.
    if not 0<=value<124:return None
    pointer=u16(rom.data,pc(0x03D636)+value*2)
    return 0x030000|pointer if pointer>=0x8000 else None
