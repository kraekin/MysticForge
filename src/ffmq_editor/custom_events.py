"""Structured, bounded custom NPC event compiler. No arbitrary bytecode input."""
from .rom import pc,FormatError

GUARDS={
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
   if node['kind']=='say' and node.get('speaker')=='object':
    if any(area!=node['speaker_area'] for area in areas):raise FormatError('An NPC speaker belongs to a different map setup. Choose a speaker on this map.')
   if node['kind']=='if_flag':visit(node['then']);visit(node['otherwise'])
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
   kind=n.get('kind');keys={'say':{'text'},'set_flag':{'flag'},'clear_flag':{'flag'},'if_flag':{'flag','then','otherwise'},'wait':{'frames'},'call_text':{'npc'},'face_player':{'direction'},'end':set()}.get(kind)
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
   elif kind=='face_player':emit(bytes((0x2c,field(n,'direction',0,3)<<4,0x54)))
   elif kind=='end':emit(b'\x00')
   elif kind in ('set_flag','clear_flag'):emit(bytes((0x23 if kind=='set_flag' else 0x2b,field(n,'flag',0,255))))
   elif kind=='wait':emit(bytes((5,0xe1,field(n,'frames',1,255))))
   elif kind=='call_text':
    ident=field(n,'npc',0,123);target=text_calls(p).get(ident)
    if target is None:raise FormatError('Only verified text-only NPC events can be called in this version.')
    emit(bytes.fromhex('0731a803')+b'\x07'+target[0].to_bytes(3,'little')+bytes.fromhex('07578403'))
   else:
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
 if k=='say':return speaker_label(n)+' says: '+n['text'].replace('\n',' / ')[:100]
 if k=='if_flag':return 'If '+flag_label(n['flag'])+(' is set' if n.get('is_set',True) else ' is clear')
 if k in ('set_flag','clear_flag'):return ('Set ' if k=='set_flag' else 'Clear ')+flag_label(n['flag'])
 if k=='face_player':return 'Turn hero '+('up','right','down','left')[n['direction']]
 if k=='end':return 'End conversation here'
 if k=='wait':return f"Wait {n['frames']} frames"
 return f"Show existing NPC dialogue ${n['npc']:02X}"
