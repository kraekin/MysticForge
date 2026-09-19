"""Verified movement encoding and length-preserving original scene edits."""
from .rom import pc,FormatError
from .field_actions import field_action
GUARDS={
 0x01c02f:'e220c210a9108d9319adef1929038d8b0e8dd719a9408d2919a9018d2819a9018d2a198df719a900ebadee194a4a4a4aa85a2072c0205c937a88d0f59c29199c2a1960',
 0x01bb95:'e220c210209dcf9054bd721a48a9109d721abd801a29cf9d801aadef1929038d2b190a0a0a0a1d801a9d801a2081cca900ebadee194a4a4a4aa85ada0820ecca20cf8228fabd721ad0f17a88f00b5aa9109d721a2081cc80e2689d',
 0x01bbf3:'adee1929f0004a4a4aaa7c00bc1abc1abc1abc1abc34bc34bc',
}
def verify(p):
 for at,h in GUARDS.items():
  raw=bytes.fromhex(h)
  if p.base_rom.data[pc(at):pc(at)+len(raw)]!=raw:raise FormatError('Movement handler guard failed.')

def family(action,value):
 if action in (0x26,0x27):return ('audio',action)
 if 0x40<=action<=0x43:return ('walk',0x40)
 if 0x50<=action<=0x53:return ('walk',0x50)
 if 0x47<=action<=0x4a:return ('walk',0x47)
 if 0x57<=action<=0x5a:return ('walk',0x57)
 if action in (0x44,0x54) and value>>4<4:return ('turn',action)
 return None

def pairs(raw):
 if len(raw)==3 and raw[0]==0x2c:return [1]
 if len(raw)>=3 and raw[0]==0x2a and raw[-2:]==b'\xff\xff' and len(raw)%2:return list(range(1,len(raw)-2,2))
 return []

def editable(raw):return any(family(raw[i+1],raw[i]) for i in pairs(raw))

def replace(p,original,value):
 verify(p)
 if not isinstance(value,list) or len(value)!=len(original) or any(type(b) is not int or not 0<=b<=255 for b in value):raise FormatError('Invalid scene command data.')
 raw=bytes(value);allowed=set()
 for i in pairs(original):
  old,arg=original[i+1],original[i];f=family(old,arg)
  if f is None:continue
  allowed.update((i,i+1));kind,base=f
  if kind=='audio':
   from .custom_events import verify as verify_audio
   verify_audio(p)
   if raw[i+1]!=old or raw[i] not in [value for value,_ in options(f,arg)]:raise FormatError('Choose a verified audio ID; the command type stays fixed.')
   continue
  if raw[i]&15!=arg&15:raise FormatError('Original scene actor references must be preserved.')
  if kind=='walk':
   if not base<=raw[i+1]<=base+3 or raw[i]>>4==0:raise FormatError('Walks require a verified direction and 1–15 tiles.')
  elif raw[i+1]!=old or raw[i]>>4>3:raise FormatError('Choose a facing direction, not an unverified pose.')
 if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(original,raw))):raise FormatError('Protected scene commands, calls and terminators cannot change.')
 return raw

def movement(p,node):
 verify(p);kind=node['kind'];direction=node['direction']
 if type(direction) is not int or not 0<=direction<=3:raise FormatError('Choose a movement direction.')
 player=kind=='walk_player';slot=0
 if not player:
  area=node['actor_area'];slot=node['actor_object']
  if type(area) is not int or not 0<=area<len(p.rom.areas) or type(slot) is not int or not 0<=slot<min(16,len(p.objects(area))):raise FormatError('Choose an existing object slot on this map.')
 if kind=='turn_object':return bytes((0x2c,(direction<<4)|slot,0x44))
 count=node['tiles']
 if type(count) is not int or not 1<=count<=63:raise FormatError('Walk between 1 and 63 tiles.')
 result=bytearray()
 while count:
  n=min(15,count);result.extend((0x2c,(n<<4)|slot,(0x50 if player else 0x40)+direction));count-=n
 return bytes(result)


def options(f,original):
 if f and f[0]=='audio':
  from .custom_events import MUSIC_IDS,SOUND_IDS
  ids=MUSIC_IDS if f[1]==0x26 else SOUND_IDS
  noun='Music track' if f[1]==0x26 else 'Sound effect'
  return [(i,f'{noun} ${i:02X}'+(' (original)' if i==original else '')) for i in sorted(set(ids)|{original})]
 return list(enumerate(('Up','Right','Down','Left')))
