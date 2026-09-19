"""Structured, bounded custom NPC event compiler. No arbitrary bytecode input."""
from .rom import pc,FormatError

# Only IDs observed in decoded original field event sequences are offered.
MUSIC_IDS=(5,12,19,20)
SOUND_IDS=(5,8,11,12,18,20,21,22,23,27,37,39,40,43,48)
BRANCHES={
 'if_flag':(('then','Then — condition matches'),('otherwise','Otherwise — condition does not match')),
 'choice':(('yes','Yes'),('no','No / Cancel')),
 'give_item':(('received','Received — at least one added'),('full','Cannot carry — nothing added')),
}

def branches(node):return BRANCHES.get(node['kind'],())

GUARDS={
 0x00dad1:'e220ce6601a59ec910902ac914901cc9dd9022f00badb010200adb8db0108015ad3010200adb8d3010800a226ada00200adb9d9f0eee660160c963900b9c6601a9801c6501a963606d6601c964900ce96349ff6d66018d6601a96360a59e226ada00c963009006a9ff00859e60a59e08c230da5ae230c910903cc9149026c9209040c92f904ac9dd9068d00cad3010c963b077ee30108072adb010c963b06beeb0108066a8226ada00c963b05d989d9e0efe9f0e80540bf4a60e2b224e97002b8048e9130bf438102b224e97002b803a48c926f03b38e9200bf432102b224e97002b688d3110a000201191a9040cd400801848e92e0bf435102b224e97002b68a000201191a9040cd400c2307afa286048a9021cb210',
 0x00da6a:'08e230c9fff020c9ddb025a200dd9e0ef019e8e8e008d0f5a9ffa200dd9e0ef006e8e8e008d0f5a9008013bd9f0e800ed007ad3010a2928005adb010a212286b',
 0x038dac:'29020f6001054a5f01057e1104000c0300010d010000000fb400054fb30012610110c40005a0c000d98d10c2001263010f5f01057f0550610105456301126301296a30176a051db6000208618e05e3100700055a8000050900278e05fd4b188e100700055a0080050900338e100700055a000c057d004f8e0af98d051eb60002083f8e0f020000051eb60002083f8e053bff000524b600ba00020cb800001702174b00',
 0x01b4d1:'adee1929ff000aaa7cdcb4f6b41ab51bb524b524b524b531b531b531b51ab51ab5f6b41ab5a01000ad0019aa8a38e902008d001920cf828a186902008d001920cf8288d0e78e00196060a90a008d2b194c02d6e220c21020d882ce1001d0f860e220c21020d882ad1001c90ff005ee100180f160',
 0x01ba91:'a9080f8d010508e220c210adee19291f8d00052860adee1929ff00da08e220c210a20f888e06058d050528fa60',

 0x00a168:'a717e61729ff00e220854fc230a90300a231a84c1ca7a717e61729ff00e220854fc230a90300a295a84c1ca7',
 0x00a874:'a717e617e617aaaf67337ea8a717e61729ff003a8b547e00ab98c9d93590034c1f9d8f67337e60',
 0x00a89b:'a717e617e617a8a717e61729ff004849ffff386f67337e8f67337eaa683a54007e60',
 0x00b355:'a717e617e617c900809007aaa903004c1ca7d417d4188dee19224bb2',
 0x01c0dc:'e220c2109c2919a9108d9319adee1929f04a4a4a4a8d8b0e20cc9460',

 0x00a563:'a717e61729ff0022769700d0a98025',
 0x00aea2:'a717e61729ff002260970060',
 0x00aec7:'a717e61729ff00226b970060',
 0x00a519:'a717851760',
 0x00a708:'a717e617e617aaa717e61729ff008004',
 0x00a29b:'a717e61729ff0022a096003ad0f960',
 0x009b9d:'31a803578403',
}

def verify(p):
 for at,h in GUARDS.items():
  raw=bytes.fromhex(h)
  if p.base_rom.data[pc(at):pc(at)+len(raw)]!=raw:raise FormatError(f'Custom event handler guard failed at ${at:06X}.')

def text_calls(p):
 """Only original NPC routines consisting entirely of text plus return."""
 cached=getattr(p.base_rom,'_custom_text_calls',None)
 if cached is not None:return cached
 from .events import npc_entry,decode
 from .event_editing import tokens
 result={}
 for ident in range(124):
  entry=npc_entry(p.base_rom,ident)
  if entry is None:continue
  rows=decode(p.base_rom,entry,limit=8192,follow_calls=False)
  cursor=entry
  for row in rows:
   if not row.complete or row.address!=cursor:break
   cursor+=len(row.raw)
  else:
   if rows and rows[-1].raw==b'\x00':
    text=tokens(p.base_rom,b''.join(r.raw for r in rows[:-1]))
    if text:result[ident]=(entry,text)
 p.base_rom._custom_text_calls=result;return result

def speaker_reference(p,area,index):
 if type(area) is not int or not 0<=area<len(p.rom.areas) or type(index) is not int:raise FormatError('Invalid speaker map or object.')
 objects=p.objects(area)
 if not 0<=index<len(objects):raise FormatError('The speaker object no longer exists.')
 obj=objects[index];ident=obj[1]
 if (obj[5]>>3)&3 or ident==0:raise FormatError('Choose an NPC speaker with a nonzero interaction ID.')
 if sum(o[1]==ident for o in objects)!=1:raise FormatError('This speaker shares an interaction ID with another object; its speech position would be ambiguous.')
 return ident


def validate_speaker_maps(record,areas):
 """Call after record compilation, which validates the tree shape."""
 def visit(nodes):
  for node in nodes:
   if node['kind'] in ('walk_object','turn_object') and any(area!=node['actor_area'] for area in areas):raise FormatError('The movement object belongs to a different map setup.')
   if node['kind']=='say' and node.get('speaker')=='object':
    if any(area!=node['speaker_area'] for area in areas):raise FormatError('An NPC speaker belongs to a different map setup. Choose a speaker on this map.')
   for key,_ in branches(node):visit(node[key])
 visit(record.get('actions',[]))

def speaker_label(n):
 mode=n.get('speaker','npc')
 if mode=='hero':return 'Hero'
 if mode=='object':return f"Object ${n['speaker_object']:02X} in area ${n['speaker_area']:02X}"
 return 'This NPC'

def compile_actions(p,actions,address):
 from .private_dialogue import compile_text
 if type(address) is not int or address>>16!=0x1f or not 0xc400<=address&65535<=0xffff:raise FormatError('Custom event address is outside its allocated bank.')
 verify(p);raw=bytearray(b'\x04');count=0
 def emit(data):raw.extend(data)
 def pointer():
  value=(address&65535)+len(raw)
  if value>65535:raise FormatError('Custom event exceeds its ROM bank.')
  return value.to_bytes(2,'little')
 def field(node,key,lo,hi):
  v=node[key]
  if type(v) is not int or not lo<=v<=hi:raise FormatError(f'Invalid {key} value.')
  return v
 def body(nodes,depth):
  nonlocal count
  if not isinstance(nodes,list) or depth>8:raise FormatError('Use at most eight nested conditions.')
  for n in nodes:
   count+=1
   if count>256 or not isinstance(n,dict):raise FormatError('An event supports at most 256 actions.')
   kind=n.get('kind');keys={'say':{'text'},'set_flag':{'flag'},'clear_flag':{'flag'},'if_flag':{'flag','then','otherwise'},'wait':{'frames'},'call_text':{'npc'},'face_player':{'direction'},'walk_player':{'direction','tiles'},'walk_object':{'direction','tiles','actor_area','actor_object'},'turn_object':{'direction','actor_area','actor_object'},'end':set(),'choice':{'text','yes','no'},'give_item':{'item','quantity','received','full'},'music':{'id'},'sound':{'id'},'screen':{'effect'}}.get(kind)
   optional={'speaker','speaker_area','speaker_object'} if kind=='say' else {'is_set'} if kind=='if_flag' else set()
   if keys is None or not keys|{'kind'}<=set(n) or set(n)-(keys|{'kind'}|optional):raise FormatError('Unsupported custom event action or fields.')
   if kind=='say':
    mode=n.get('speaker','npc')
    if mode not in ('npc','hero','object'):raise FormatError('Invalid dialogue speaker.')
    if mode!='object' and ('speaker_area' in n or 'speaker_object' in n):raise FormatError('Unexpected speaker object fields.')
    if mode=='object' and not {'speaker_area','speaker_object'}<=set(n):raise FormatError('Choose a speaker object.')
    if mode=='npc':emit(bytes.fromhex('0731a803'))
    else:
     # Preserve both bytes: window helpers copy $4F..$50 into their actor reference.
     emit(bytes.fromhex('051d4f0002'))
     ident=0 if mode=='hero' else speaker_reference(p,n['speaker_area'],n['speaker_object'])
     emit(bytes((0x1b if mode=='hero' else 0x1a,ident)))
    emit(compile_text(n['text'])[:-1]+bytes.fromhex('07578403'))
    if mode!='npc':emit(bytes.fromhex('051e4f0002'))
   elif kind=='choice':
    # Original band NPC $03EB2E: alternate window, two rows, $038DAC menu.
    # Close/restore on BOTH paths before user actions (including early returns).
    emit(bytes.fromhex('0731a803')+compile_text(n['text'])[:-1])
    emit(bytes.fromhex('051d4f00021b00070ea803'))
    emit(compile_text('   Yes\n   No')[:-1])
    emit(bytes.fromhex('0d5f010102174b07ac8d03'))
    emit(bytes.fromhex('0b00'));yes_at=len(raw);emit(b'\x00\x00')
    cleanup=bytes.fromhex('07578403051e4f0002')
    emit(cleanup);body(n['no'],depth+1);emit(b'\x0a');end_at=len(raw);emit(b'\x00\x00')
    raw[yes_at:yes_at+2]=pointer();emit(cleanup);body(n['yes'],depth+1);raw[end_at:end_at+2]=pointer()
   elif kind=='give_item':
    item=field(n,'item',0,63);quantity=field(n,'quantity',1,99)
    if item not in range(0x10,0x14) and quantity!=1:raise FormatError('Only potions, seeds and refreshers support quantities greater than one.')
    # Native $00DB2D checks 99 then grants the first item. $00DAD1 adds
    # the remainder, clamping consumables at 99. No chest collection flags.
    emit(bytes((0x0d,0x65,1,0,quantity,5,0x3b,item)))
    emit(bytes.fromhex('092ddb000bff'));full_at=len(raw);emit(b'\x00\x00')
    emit(bytes.fromhex('09d1da00'));body(n['received'],depth+1)
    emit(b'\x0a');end_at=len(raw);emit(b'\x00\x00')
    raw[full_at:full_at+2]=pointer();body(n['full'],depth+1);raw[end_at:end_at+2]=pointer()
   elif kind in ('music','sound'):
    ident=field(n,'id',0,255)
    if ident not in (MUSIC_IDS if kind=='music' else SOUND_IDS):raise FormatError('Choose an audio ID verified in original field events.')
    emit(bytes((0x2c,ident,0x26 if kind=='music' else 0x27)))
   elif kind=='screen':
    if n['effect']=='shake':emit(bytes.fromhex('2c0020'))
    elif n['effect']=='fade':
     # Start at full brightness: native fade-out decrements before testing.
     # A single paired action cannot strand subsequent dialogue in darkness.
     emit(bytes.fromhex('0c10010f2c032005e11e2c0620'))
    else:raise FormatError('Choose screen shake or fade out and back in.')
   elif kind in ('walk_player','walk_object','turn_object'):
    from .scene_commands import movement
    emit(movement(p,n))
   elif kind=='face_player':emit(bytes((0x2c,field(n,'direction',0,3)<<4,0x54)))
   elif kind=='end':emit(b'\x00')
   elif kind in ('set_flag','clear_flag'):emit(bytes((0x23 if kind=='set_flag' else 0x2b,field(n,'flag',0,255))))
   elif kind=='wait':emit(bytes((5,0xe1,field(n,'frames',1,255))))
   elif kind=='call_text':
    ident=field(n,'npc',0,123);target=text_calls(p).get(ident)
    if target is None:raise FormatError('Only verified text-only NPC events can be called in this version.')
    emit(bytes.fromhex('0731a803')+b'\x07'+target[0].to_bytes(3,'little')+bytes.fromhex('07578403'))
   elif kind=='if_flag':
    # Branch if set to Then; Otherwise falls through. Each fixup is rebuilt.
    emit(bytes((0x2e,field(n,'flag',0,255))));to_then=len(raw);emit(b'\x00\x00')
    is_set=n.get('is_set',True)
    if type(is_set) is not bool:raise FormatError('Choose whether the flag must be set or clear.')
    body(n['otherwise' if is_set else 'then'],depth+1);emit(b'\x0a');to_end=len(raw);emit(b'\x00\x00')
    raw[to_then:to_then+2]=pointer();body(n['then' if is_set else 'otherwise'],depth+1);raw[to_end:to_end+2]=pointer()
 body(actions,0);emit(b'\x00')
 if (address&65535)+len(raw)>0x10000:raise FormatError('Custom event exceeds its ROM bank.')
 return bytes(raw)

def record_bytes(p,record,address):
 from .private_dialogue import compile_text
 if not isinstance(record,dict):raise FormatError('Invalid custom NPC event.')
 if set(record)=={'text'}:return compile_text(record['text'])
 if set(record)=={'actions'}:return compile_actions(p,record['actions'],address)
 raise FormatError('Invalid custom NPC event fields.')

def label(n):
 from .event_flags import flag_label
 k=n['kind']
 if k=='choice':return 'Ask Yes / No: '+n['text'].replace('\n',' / ')[:100]
 if k=='give_item':return f"Give item ${n['item']:02X} × {n['quantity']}"
 if k in ('music','sound'):return f"Play {'music track' if k=='music' else 'sound effect'} ${n['id']:02X}"
 if k=='screen':return 'Shake screen' if n['effect']=='shake' else 'Fade out and back in'
 if k=='say':return speaker_label(n)+' says: '+n['text'].replace('\n',' / ')[:100]
 if k=='if_flag':return 'If '+flag_label(n['flag'])+(' is set' if n.get('is_set',True) else ' is clear')
 if k in ('set_flag','clear_flag'):return ('Set ' if k=='set_flag' else 'Clear ')+flag_label(n['flag'])
 if k in ('walk_player','walk_object','turn_object'):
  who='hero' if k=='walk_player' else f"object ${n['actor_object']:02X}"
  return ('Turn ' if k=='turn_object' else 'Walk ')+who+' '+('up','right','down','left')[n['direction']]+('' if k=='turn_object' else f" · {n['tiles']} tiles")
 if k=='face_player':return 'Turn hero '+('up','right','down','left')[n['direction']]
 if k=='end':return 'End conversation here'
 if k=='wait':return f"Wait {n['frames']} frames"
 return f"Show existing NPC dialogue ${n['npc']:02X}"
