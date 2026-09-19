"""Guarded Kaeli axe choreography; original story flow stays in place."""
from .rom import pc, FormatError

AREA=0x10
ENTRY=0x03DB1D
RETURN=0x03DB3E
STORAGE=0xF8700
LIMIT=0xF8800
ORIGINAL=bytes.fromhex('2a11432140414405274546204020431144ffff')
END=(10,14)
MOTHER_END=(11,12)
MOTHER_ROUTE=[[13,12],[11,12]]

def xy(obj):return (obj[3]&63,obj[2]&63)

def defaults(p):
 axe=xy(p.objects(AREA)[5]);start=xy(p.objects(AREA)[1])
 return {'axe':list(axe),'approach':[[axe[0],start[1]],[axe[0],axe[1]+1]],'return':[[axe[0],14],list(END)],'mother':[point[:] for point in MOTHER_ROUTE]}

def points(p,items,start):
 attr=p.rom.attributes[p.rom.areas[AREA].attributes_id]
 if not isinstance(items,list) or not 1<=len(items)<=24:raise FormatError('Use 1–24 route waypoints.')
 result=[tuple(start)]
 for point in items:
  if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(n) is not int for n in point):raise FormatError('Invalid route waypoint.')
  x,y=point
  if not 0<=x<attr.width or not 0<=y<attr.height:raise FormatError('A waypoint is outside the map.')
  old=result[-1]
  if x!=old[0] and y!=old[1]:raise FormatError('Each route segment must be horizontal or vertical. Add a corner waypoint.')
  if (x,y)!=old:result.append((x,y))
 return result

def route_bytes(route,slot=1):
 raw=bytearray()
 for (x,y),(xx,yy) in zip(route,route[1:]):
  direction=1 if xx>x else 3 if xx<x else 2 if yy>y else 0
  count=abs(xx-x)+abs(yy-y)
  while count:
   step=min(15,count);raw.extend((0x2c,(step<<4)|slot,0x40+direction));count-=step
 return bytes(raw)

def verify(p):
 if p.base_rom.data[pc(ENTRY):pc(ENTRY)+len(ORIGINAL)]!=ORIGINAL or p.base_rom.data[pc(RETURN):pc(RETURN)+3]!=bytes.fromhex('2c2142'):raise FormatError('Kaeli scene source guard failed.')
 # Native object walker: slot lookup, tile repeat count, synchronous completion.
 guards={0x01bb95:'e220c210209dcf9054',0x01bb9e:'bd721a48a9109d721abd801a29cf9d801a',0x01bbcf:'5ada0820ecca20cf8228fabd721ad0f17a88f00b'}
 for at,text in guards.items():
  raw=bytes.fromhex(text)
  if p.base_rom.data[pc(at):pc(at)+len(raw)]!=raw:raise FormatError(f'Scene movement guard failed at ${at:06X}.')
 from .event_editing import index
 idx=index(p)
 if any(ENTRY<a<ENTRY+len(ORIGINAL) for a in idx.incoming):raise FormatError('Another event enters the middle of the protected scene.')

def validate(p):
 if p.story_scene is None:return
 if not p.expanded:raise FormatError('Story movement editing requires expanded export.')
 verify(p);r=p.story_scene
 if not isinstance(r,dict) or set(r) not in ({'axe','approach','return'},{'axe','approach','return','mother'}):raise FormatError('Invalid Kaeli scene record.')
 objects=p.objects(AREA)
 if len(objects)<6:raise FormatError('Kaeli scene actors were removed.')
 # Compare against a clean project; immutable base data, no recursive scene.
 from .project import Project
 clean=Project(p.base_rom).objects(AREA)
 for i in (0,1,5):
  expected=bytes(clean[i]);current=bytes(objects[i])
  if i==5:
   if any((current[j]&mask)!=(expected[j]&mask) for j,mask in enumerate((255,255,192,192,255,255,255))):raise FormatError('The axe object identity or behavior changed. Restore it before editing this scene.')
  elif current!=expected:raise FormatError('Kaeli or her mother moved or changed. This scene currently requires their original starting setup.')
 if not isinstance(r['axe'],list) or len(r['axe'])!=2 or any(type(n) is not int for n in r['axe']):raise FormatError('Invalid axe position.')
 if tuple(r['axe'])!=xy(objects[5]):raise FormatError('The axe moved outside the scene editor. Reopen Kaeli’s axe scene to update its route.')
 approach=points(p,r['approach'],xy(objects[1]));back=points(p,r['return'],approach[-1])
 if approach[-1]!=(r['axe'][0],r['axe'][1]+1):raise FormatError('The approach must finish directly below the axe.')
 if back[-1]!=END:raise FormatError('The return route must finish at (10, 14) to preserve the remaining story.')
 mother=points(p,r.get('mother',MOTHER_ROUTE),xy(objects[0]))
 if mother[-1]!=MOTHER_END:raise FormatError('Her mother’s route must finish at (11, 12) to preserve the remaining scene.')
 # Original dialogue replacement would skip this scene entirely.
 if objects[1][1] in p.private_dialogues:raise FormatError('Kaeli has a custom event; restore her original interaction first.')
 for at,edit in p.event_edits.items():
  end=at+len(bytes.fromhex(edit['bytes']))
  if at<ENTRY+len(ORIGINAL) and end>ENTRY or at<RETURN+3 and end>RETURN:raise FormatError('An event edit overlaps Kaeli’s protected movement.')
 a=route_bytes(approach)+bytes.fromhex('2c41442c05272c4546')+route_bytes(mother,0)+bytes.fromhex('2c114400')
 b=route_bytes(back)+b'\x00'
 if len(a)+len(b)>LIMIT-STORAGE:raise FormatError('Routes exceed the protected 256-byte scene budget.')
 return a,b

def writes(p):
 if p.story_scene is None:return []
 a,b=validate(p);cpu=0x1f8700
 # Long-call approach, skip the return trampoline; later original short call
 # invokes that trampoline and resumes at the original companion/story code.
 stub=b'\x07'+cpu.to_bytes(3,'little')+b'\x0a'+((ENTRY+len(ORIGINAL))&65535).to_bytes(2,'little')
 stub+=b'\x07'+(cpu+len(a)).to_bytes(3,'little')+b'\x00'
 stub+=b'\x04'*(len(ORIGINAL)-len(stub))
 return [(pc(ENTRY),stub,'Kaeli approach / return trampoline'),(pc(RETURN),b'\x08'+((ENTRY+7)&65535).to_bytes(2,'little'),'Kaeli return call'),(STORAGE,a+b,'Kaeli movement routes')]

def apply(p,record):
 from copy import deepcopy
 from .object_editor import field_changes
 before=deepcopy((p.story_scene,p.edits,p.content))
 try:
  p.story_scene=deepcopy(record)
  for key,(_,value) in field_changes(p,AREA,5,{'X':record['axe'][0],'Y':record['axe'][1]}).items():p.set(key,value)
  validate(p)
 except (ValueError,KeyError,TypeError,IndexError):
  p.story_scene,p.edits,p.content=before
  raise
