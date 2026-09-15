"""Readable event rows without changing the instruction decoder or ROM."""
from dataclasses import dataclass,replace
from .events import fragments,text_fragment,inline_name,decode,Instruction
from .rom import pc,read
from .field_actions import field_action
from .event_flags import name_flags

def literal_text(rom,raw,seen=frozenset()):
    """Expand only text and formatting. Never execute calls or conditions."""
    dictionary=fragments(rom);parts=[]
    cursor=0
    while cursor<len(raw):
        byte=raw[cursor];cursor+=1
        if byte>=0x80:parts.append(text_fragment(bytes([byte])))
        elif byte in (0x1d,0x1e,0x1f,0x20):
            if cursor>=len(raw):return None
            name=inline_name(rom,byte,raw[cursor]);cursor+=1
            if name is None:return None
            parts.append(name)
        elif byte in (1,2):parts.append('\n'*byte)
        elif byte==3:parts.append(' ')
        elif byte==6:parts.append('[line break or space]')
        elif byte==5 and cursor+3<len(raw) and raw[cursor]==0x18:
            address=int.from_bytes(raw[cursor+1:cursor+3],'little');length=raw[cursor+3]
            names={(0x1000,8):'[Hero name]',(0x1080,8):'[Companion name]',(0x0066,8):'[Number]'}
            if (address,length) not in names:return None
            parts.append(names[address,length]);cursor+=4
        elif byte==5 and cursor+1<len(raw) and raw[cursor]==0x75:
            parts.append(text_fragment(raw[cursor+1:cursor+2]));cursor+=2
        elif 0x30<=byte<0x80:
            index=byte-0x30
            if index>=len(dictionary):return None
            if index in seen:return None
            address,length=dictionary[index]
            text=literal_text(rom,read(rom.data,pc(address),length),seen|{index})
            if text is None:return None
            parts.append(text)
        else:return None
    return ''.join(parts)

@dataclass
class Dialogue:
    address:int
    text:str
    instructions:tuple

def expanded_rows(rom,row,seen=frozenset()):
    """Expose punctuation AND actions inside mixed fragments in source order."""
    if row.text is not None:
        yield row;return
    if len(row.raw)==1 and 0x30<=row.raw[0]<0x80 and literal_text(rom,row.raw) is None:
        index=row.raw[0]-0x30
        if index>=len(fragments(rom)):
            yield row;return
        if index in seen:
            yield Instruction(row.address,row.raw,'Recursive text fragment · expansion stopped',(),False);return
        address,length=fragments(rom)[index]
        for child in decode(rom,address,follow_calls=False):
            yield from expanded_rows(rom,child,seen|{index})
        return
    # These are actual engine helper addresses, not guessed from text tokens.
    helpers={0x038457:'Close dialogue message',
             0x03a80e:'Advance dialogue page / scroll to the next text position (current window state)',
             0x0384c2:'Switch active dialogue window',
             0x0383e7:'Update primary dialogue window',
             0x0383f7:'Update alternate dialogue window'}
    calls=[target for label,target in row.edges if label in ('call','jump')]
    inserts={0x0381d6:'[Number]',0x0382bb:'[Location name from runtime index]',
             0x038383:'[Item / ability name from runtime index]',
             0x03a7f6:'[Character name from runtime index]',0x03a802:'[Enemy name from runtime index]'}
    if len(calls)==1 and calls[0] in inserts and row.raw and row.raw[0] in (7,8):
        yield replace(row,text=inserts[calls[0]]);return
    if row.raw[:2]==b'\x05\xea':
        bounded=[target for label,target in row.edges if label=='bounded']
        if bounded:
            text=literal_text(rom,read(rom.data,pc(bounded[0]),row.raw[2]))
            if text is not None:
                yield replace(row,text=text);return
        yield replace(row,text=f'[Runtime text: {row.raw[2]} bytes]');return
    if row.raw[:2]==b'\x05\x18' and literal_text(rom,row.raw) is None:
        yield replace(row,text=f'[Runtime text at ${int.from_bytes(row.raw[2:4],"little"):04X}: {row.raw[4]} bytes]');return
    if len(calls)==1 and calls[0] in helpers and row.raw and row.raw[0] in (7,8,0x1c):
        yield Instruction(row.address,row.raw,helpers[calls[0]],row.edges,row.complete);return
    yield row

def readable_rows(rom,rows):
    """Join adjacent literal runs, never across branch targets or event actions."""
    targets={target for r in rows for label,target in r.edges if label not in ('next','call','fragment')}
    output=[];pending=[];parts=[];end=None
    def flush():
        if pending:output.append(Dialogue(pending[0].address,''.join(parts),tuple(pending)));pending.clear();parts.clear()
    for row in sorted(rows,key=lambda r:r.address):
        if row.address in targets or (end is not None and row.address!=end):flush()
        if row.complete and row.raw[:1]==b'\x2a':
            # Show each native command in sequence order. These presentation
            # rows carry no fabricated opcode bytes; Technical details retains
            # the complete original $2A instruction and its terminator.
            flush()
            for i in range(1,len(row.raw)-2,2):
                value=int.from_bytes(row.raw[i:i+2],'little')
                caption=name_flags(field_action(value>>8,value&255)) if value<0x8000 else 'Call event in this field sequence'
                edges=() if value<0x8000 else (('call',0x030000|value),)
                output.append(Instruction(row.address+i,b'',f'Sequence step {(i+1)//2}: {caption}',edges))
            end=row.address+len(row.raw);continue
        for part in expanded_rows(rom,row):
            text=part.text if part.text is not None else literal_text(rom,part.raw) if part.raw else None
            if text is None:flush();output.append(part)
            else:pending.append(part);parts.append(text)
        end=row.address+len(row.raw)
    flush();return output

def technical_setup(row):
    if isinstance(row,Dialogue) or not row.complete or any(k!='next' for k,_ in row.edges):return False
    if 'interaction reference' in row.description:return False
    return row.description.startswith(('No operation','Push engine memory','Pop dialogue stack',
        'Set working','Load working','Write byte','Write word','Write 24-bit','Store working',
        'Set interpreter control','Clear interpreter control','Set text palette','Set text position',
        'Set text window','Set text attribute','Set text display','Set text character','Set dialogue vertical',
        'Select flag context','Select item-flag context','Prepare dialogue graphics','Upload pending',
        'Extend dialogue upload','Wait for dialogue engine synchronization'))
