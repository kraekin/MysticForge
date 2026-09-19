"""Conservative scene timeline: address order, never a simulated execution trace."""
from dataclasses import dataclass
from .events import decode
from .event_editing import index,event_rom,tokens
from .scene_commands import pairs,family
from .field_actions import field_action
@dataclass(frozen=True)
class Step:
 address:int
 label:str
 segment:object=None
 pair:int|None=None
 links:tuple=()
 link_extent:int|None=None

def steps(p,entry,extent=None):
 segments=index(p).segments;rom=event_rom(p);out=[];covered=-1
 for row in sorted(decode(rom,entry,limit=8192,follow_calls=False,extent=extent),key=lambda r:r.address):
  if row.address<covered:continue
  s=segments.get(row.address)
  if s and extent is not None and s.address+len(s.raw)>entry+extent:s=None
  if s and s.kind=='text':
   value=p.event_edits.get(s.address,{}).get('value',tokens(p.base_rom,s.raw));out.append(Step(row.address,'Dialogue: '+value.replace('\n',' / '),s));covered=s.address+len(s.raw);continue
  offsets=pairs(row.raw)
  if offsets:
   for i in offsets:
    arg,action=row.raw[i:i+2];label=field_action(action,arg) if action<128 else f'Call scene routine ${(action<<8)|arg:04X}'
    links=(('call',(row.address&0xff0000)|(action<<8)|arg),) if action>=128 else ()
    out.append(Step(row.address,label,s if s and s.kind=='field' else None,i,links))
  else:out.append(Step(row.address,row.description,s,None,tuple((kind,at) for kind,at in row.edges if kind!='next'),row.raw[-1] if row.raw and any(kind=='bounded' for kind,_ in row.edges) else None))
 return out

def walk_context(p,step):
 """Only a direct transition within this same command group establishes hero position."""
 if not step.segment or step.pair is None:return None
 raw=bytes(p.event_edits.get(step.address,{}).get('value',step.segment.raw));positions={};area=None
 from .connections import Connections
 c=Connections(p.rom);c.project=p
 for i in pairs(raw):
  arg,action=raw[i:i+2];f=family(action,arg);actor='hero' if 0x50<=action<=0x5e else arg&15
  if i==step.pair:return (area,positions.get(actor)) if area is not None and actor in positions else None
  if action in (0,1,2,4,5,6):
   target=c.destination(action,arg)
   positions={};area=None
   if target:area,x,y,_=target;positions['hero']=(x,y)
  elif f and f[0]=='walk':
   if actor in positions:
    dx,dy=((0,-1),(1,0),(0,1),(-1,0))[action-f[1]];x,y=positions[actor];positions[actor]=(x+dx*(arg>>4),y+dy*(arg>>4))
  elif f and f[0]=='turn':pass
  elif action in (0x20,0x26,0x27):pass
  else:positions={}
 return None
