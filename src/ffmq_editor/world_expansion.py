"""Guarded bank-local overworld tables; seven optional nodes, stable original IDs."""
from .rom import pc,FormatError
from .layout_storage import cpu_address
START=0xd0000
POINTERS=START
POSITIONS=START+0x200
GATES=START+0x300
ACTIONS=START+0x500
STREAMS=START+0x600
PATCHES=((0x01f147,0x07f011,POINTERS),(0x01f14f,0x070000,0x1a0000),(0x01f531,0x070000,0x1a0000),
 (0x0b8177,0x07f7c3,POSITIONS),(0x01f1b6,0x07efa1,ACTIONS),(0x0289fe,0x07efa1,ACTIONS),
 *((a,0x07ee84+i,GATES+i) for i,a in enumerate((0x0c802d,0x0c8034,0x0c803e,0x0c8048,0x0c8052))))
def active(p):return bool(p.world['routes'] or p.world['nodes'])
def nodes(p):return (*range(1,57),*sorted(p.world['nodes']))
def route_data(p,r):return p.world['routes'].get(r.node*4+r.direction,b'\0' if r.node>56 else p.fixed('world_route',r.offset))
def routes(p):
 from .world import Route
 return (*p.rom.routes,*(Route(n,d,0x300000+n*4+d,1) for n in sorted(p.world['nodes']) for d in range(4)))
def validate_structure(p):
 w=p.world
 if not isinstance(w,dict) or set(w)!={'routes','nodes'} or any(not isinstance(v,dict) for v in w.values()):raise FormatError('Invalid overworld data')
 if active(p) and not p.expanded:raise FormatError('Overworld expansion requires 1 MiB export')
 for n,c in w['nodes'].items():
  if type(n) is not int or not 57<=n<=63 or not isinstance(c,dict) or set(c)!={'position','gates','action','name'}:raise FormatError('Invalid expanded world node')
  for key,size in (('position',2),('gates',4),('action',2)):
   if not isinstance(c[key],bytes) or len(c[key])!=size:raise FormatError('Invalid expanded node data')
  if type(c['name']) is not int or not 1<=c['name']<=56:raise FormatError('Choose an existing location label')
  x,y=p.fixed('world_node',n)
  if x>=64 or y>=48:raise FormatError('World position outside map')
  value,action=p.fixed('world_action',n)
  from .connections import Connections
  links=Connections(p.rom);links.project=p
  if action not in (0,1,2,4,5) or links.destination(action,value) is None:raise FormatError('New location needs a valid direct destination')
 for key,raw in w['routes'].items():
  if type(key) is not int or key//4 not in nodes(p) or not isinstance(raw,bytes) or not 1<=len(raw)<=129:raise FormatError('Invalid expanded route')
def encode(p):return {'routes':[[k,v.hex()] for k,v in sorted(p.world['routes'].items())],'nodes':[[k,{f:(v.hex() if isinstance(v,bytes) else v) for f,v in c.items()}] for k,c in sorted(p.world['nodes'].items())]}
def decode(raw):
 try:
  w={'routes':{},'nodes':{}}
  for k,v in raw['routes']:
   if k in w['routes']:raise ValueError('Duplicate route')
   w['routes'][k]=bytes.fromhex(v)
  for k,v in raw['nodes']:
   if k in w['nodes']:raise ValueError('Duplicate node')
   w['nodes'][k]={f:bytes.fromhex(x) if f!='name' else x for f,x in v.items()}
  return w
 except (KeyError,TypeError,ValueError) as e:raise FormatError('Invalid saved overworld data') from e

def writes(p):
 from .world import validate
 validate_structure(p)
 # Preserve the original bank tail, including ship streams and their low addresses.
 bank=bytearray(b'\xff'*0x8000)
 bank[0x7234:]=p.rom.data[pc(0x07f234):pc(0x07ffff)+1]
 cursor=STREAMS
 allroutes=routes(p)
 for n in nodes(p):
  at=POINTERS+(n-1)*2;bank[at-START:at-START+2]=(cpu_address(cursor)&65535).to_bytes(2,'little')
  for d in range(4):
   r=next(r for r in allroutes if r.node==n and r.direction==d);raw=route_data(p,r);validate(p,r,raw)
   if cursor+len(raw)+1>START+0x7234:raise FormatError('Expanded overworld route bank full')
   bank[cursor-START:cursor-START+len(raw)]=raw;cursor+=len(raw)
 bank[cursor-START]=0 # final route terminator
 # Node zero and original action entries include engine-only fields.
 bank[POSITIONS-START:POSITIONS-START+114]=p.rom.data[pc(0x07f7c3):pc(0x07f7c3)+114]
 bank[GATES-START:GATES-START+285]=p.rom.data[pc(0x07ee84):pc(0x07ee84)+285]
 bank[ACTIONS-START:ACTIONS-START+112]=p.rom.data[pc(0x07efa1):pc(0x07efa1)+112]
 for n in nodes(p):
  at=POSITIONS-START+n*2;bank[at:at+2]=p.fixed('world_node',n)
  at=GATES-START+n*5
  if n>56:bank[at]=p.rom.data[pc(0x07ee84)+p.world['nodes'][n]['name']*5]
  bank[at+1:at+5]=p.fixed('world_gate',n)
  if 22<=n<=55 or n>56:
   at=ACTIONS-START+(n-1)*2;bank[at:at+2]=p.fixed('world_action',n)
 # Only these ranges are read by the patched tables/routes or preserved ship
 # pointers. Leave the other gaps to the shared expanded layout allocator.
 spans=((0,0x80,'route pointers'),(0x200,0x280,'positions'),
        (0x300,0x440,'gates'),(0x500,0x580,'actions'),
        (0x600,cursor-START+1,'route streams'),(0x7234,0x8000,'preserved ship data'))
 result=[(START+a,bytes(bank[a:b]),'expanded overworld '+label) for a,b,label in spans]
 for address,original,target in PATCHES:
  old=b'\xbf'+original.to_bytes(3,'little');at=pc(address)
  hits=[i for i in range(len(p.rom.data)) if p.rom.data.startswith(old,i)]
  expected=[pc(a) for a,o,t in PATCHES if o==original]
  if hits!=sorted(expected):raise FormatError('Unexpected overworld table consumer')
  if p.rom.data[at:at+4]!=old:raise FormatError('Overworld loader guard failed')
  target=target if target==0x1a0000 else cpu_address(target)
  result.append((at,b'\xbf'+target.to_bytes(3,'little'),'overworld table operand'))
 return result

def verify_output(p,out):
 from .world import validate
 for r in routes(p):
  pointer=int.from_bytes(out[POINTERS+(r.node-1)*2:POINTERS+r.node*2],'little');cursor=START+(pointer&32767)
  for d in range(4):
   start=cursor;cursor+=1
   while out[cursor]&128:cursor+=1
   raw=bytes(out[start:cursor])
   if d==r.direction:
    if raw!=route_data(p,r):raise FormatError('Overworld route export verification failed')
    validate(p,r,raw)
 if out[START+0x7234:START+0x8000]!=p.rom.data[pc(0x07f234):pc(0x07ffff)+1]:raise FormatError('Ship data was changed during relocation')


def add_node(p,source,direction,distance,label_source,entry_source,flag):
 from .world import position,DELTAS
 if not p.expanded:raise FormatError('Enable 1 MiB export first')
 if source not in nodes(p) or direction not in range(4) or not 1<=distance<=31 or not 1<=flag<=255:raise FormatError('Invalid new route settings')
 if not 1<=label_source<=56 or not (entry_source in p.newmaps or 22<=entry_source<=55):raise FormatError('Choose an existing location for label and entry')
 r=next(r for r in routes(p) if (r.node,r.direction)==(source,direction))
 if route_data(p,r)[0]:raise FormatError('That direction already has a route; choose an empty direction')
 action=bytes((217+p.newmaps[entry_source]['entry'],0)) if entry_source in p.newmaps else p.fixed('world_action',entry_source)
 if action[1] not in (0,1,2,4,5):raise FormatError('Choose a direct location entry; scripted entries cannot be cloned here')
 n=next((i for i in range(57,64) if i not in p.world['nodes']),None)
 if n is None:raise FormatError('All seven new overworld location slots are used')
 x,y=position(p,source);dx,dy=DELTAS[direction];x+=dx*distance;y+=dy*distance
 if not 0<=x<64 or not 0<=y<48:raise FormatError('New location is outside the overworld')
 if any(position(p,i)==(x,y) for i in nodes(p)):raise FormatError('Another overworld node already occupies this position')
 reverse=(direction+2)%4;gates=bytearray(4);gates[reverse]=flag
 p.world['nodes'][n]={'position':bytes((x,y)),'gates':bytes(gates),'action':action,'name':label_source}
 p.world['routes'][source*4+direction]=bytes((n,128|(direction<<5)|distance))
 p.world['routes'][n*4+reverse]=bytes((source,128|(reverse<<5)|distance))
 p.set(('world_gate',source,direction),flag)
 return n


def node_label(p,n):
 from .connections import Connections
 original=p.world['nodes'].get(n,{}).get('name',n)
 if 22<=original<=55:
  links=Connections(p.rom);links.project=p;value,action=p.fixed('world_action',original)
  target=links.destination(action,value,p.flags)
  if target:return f'{p.rom.areas[target[0]].name} · node ${n:02X}'
 return f'Node ${n:02X}'
