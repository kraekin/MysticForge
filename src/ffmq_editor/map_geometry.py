"""Native-size terrain copies. Coordinates remain anchored at the top-left."""
from .rom import pc,FormatError
from .layout_storage import cpu_address
SIZES=(16,32,48,64)
HOOK=0xf8500
TABLE=0xf8600

def supported(p,area):
 a=p.rom.areas[area]
 if a.layout_id==0:return 'The overworld size is fixed.'
 aliases=[other.id for other in p.rom.areas if other.offset==a.offset and other.id!=area]
 if aliases:return 'This exact area record is shared with '+', '.join(f'${i:02X}' for i in aliases)+'. Resizing is blocked until those records can be separated.'
 if area in (24,25):return 'Aquaria packs two towns in one layout; resize support needs a separate audit.'
 index=((a.header[5]&224)>>2)|((a.header[6]&224)>>5)
 if index:
  mode,graphic=p.base_rom.data[pc(0x0b844f)+(index-1)*4:pc(0x0b844f)+(index-1)*4+2]
  if mode&7==1 and graphic&128:return 'This map uses a fixed-size story background and cannot be resized yet.'
 return None

def members(p,area):
 a=p.rom.areas[area]
 return [other.id for other in p.rom.areas if other.offset==a.offset]

def check_size(width,height):
 if type(width) is not int or type(height) is not int or width not in SIZES or height not in SIZES:raise FormatError('Width and height must each be 16, 32, 48 or 64 tiles.')

def blockers(p,area,width,height):
 check_size(width,height);reason=supported(p,area)
 if reason:return [reason]
 a=p.rom.areas[area];old=p.rom.attributes[a.attributes_id]
 if width>=old.width and height>=old.height:return []
 result=[];group=members(p,area)
 # Original scripts may use coordinates or direct buffer addresses. Never claim
 # a static scan proves those safe to crop below the original geometry.
 if area<108:
  original=p.base_rom.attributes[p.base_rom.areas[area].attributes_id]
  if width<original.width or height<original.height:result.append('Original maps cannot be cropped below their original size yet: scripted coordinates need auditing.')
 for i in group:
  for j,obj in enumerate(p.objects(i)):
   if (obj[3]&63)>=width or (obj[2]&63)>=height:result.append(f'Object ${j:02X} in area ${i:02X} would be outside the map.')
  for action in p.rom.area_actions[i]:
   if action.opcode==0x22:
    change=p.rom.changes[action.value]
    if change.x+change.width>width or change.y+change.height>height:result.append(f'Story map change ${change.id:02X} would be cropped.')
 from .connections import Connections
 from .expanded_content import coordinate_id,destination_id
 offsets=set()
 for base,count,size in Connections.TABLES.values():offsets.update(pc(base)+i*size for i in range(count))
 offsets.update(destination_id(i) for i in p.content['entrances'])
 offsets.update(destination_id(c['entry']) for c in p.newmaps.values())
 for offset in offsets:
  raw=p.fixed('destination',offset)[-3:]
  if raw[0] in group and ((raw[2]&63)>=width or raw[1]>=height):result.append(f'Arrival at ({raw[2]&63}, {raw[1]}) would be outside the map.')
 for i,c in p.content['entrances'].items():
  raw=p.fixed('coordinate',coordinate_id(i))
  if c['area'] in group and (raw[0]>=width or raw[1]>=height):result.append(f'Entrance at ({raw[0]}, {raw[1]}) would be cropped.')
 return list(dict.fromkeys(result))

def resize(p,area,width,height,fill):
 if not p.expanded:raise FormatError('Resizing requires expanded ROM export.')
 problems=blockers(p,area,width,height)
 if problems:raise FormatError('\n'.join(problems))
 if type(fill) is not int or not 0<=fill<128:raise FormatError('Choose a fill tile.')
 old=p.rom.attributes[p.rom.areas[area].attributes_id]
 if (width,height)==(old.width,old.height):return
 if area not in p.layout_bindings:p.copy_terrain(area)
 resource=p.layout_id(area);group=members(p,area)
 # Independent layout can have other logical users: don't resize them silently.
 if set(p.shared_areas(resource))!=set(group):raise FormatError('This terrain copy is shared outside this area record. Make it independent before resizing.')
 cells=p.resource('layout',resource);new=bytearray([fill])*(width*height)
 for y in range(min(height,old.height)):
  count=min(width,old.width);new[y*width:y*width+count]=cells[y*old.width:y*old.width+count]
 p.edits={k:v for k,v in p.edits.items() if not(k[0]=='layout' and k[1]==resource)}
 p.layout_copies[resource]['cells']=bytes(new);p.map_sizes[resource]=(width,height)
 if area in p.newmaps:
  from .expanded_content import destination_id
  c=p.newmaps[area];raw=p.fixed('destination',destination_id(c['entry']));c.update(x=raw[2]&63,y=raw[1],facing=raw[2]>>6)
 from .new_maps import sync_catalog
 sync_catalog(p)

def validate(p):
 if p.map_sizes and not p.expanded:raise FormatError('Custom map dimensions require expanded export.')
 for resource,size in p.map_sizes.items():
  if type(resource) is not int or resource not in p.layout_copies or not isinstance(size,(tuple,list)) or len(size)!=2:raise FormatError('Invalid custom map dimensions.')
  check_size(*size)
  if len(p.layout_copies[resource]['cells'])!=size[0]*size[1]:raise FormatError('Terrain length does not match map dimensions.')
  for area in p.shared_areas(resource):
   reason=supported(p,area)
   if reason:raise FormatError(reason)
   if area<108:
    orig=p.base_rom.attributes[p.base_rom.areas[area].attributes_id]
    if size[0]<orig.width or size[1]<orig.height:raise FormatError('Original maps cannot shrink below their original dimensions.')

def writes(p):
 if not p.map_sizes:return []
 validate(p)
 original=bytes.fromhex('bf40850b')
 if p.base_rom.data[pc(0x0b8507):pc(0x0b8507)+4]!=original:raise FormatError('Dimension loader guard failed.')
 # Exact single table consumer, original 16 pairs, and 16-bit entry context.
 if p.base_rom.data.count(original)!=1 or p.base_rom.data[pc(0x0b84fb):pc(0x0b8507)]!=bytes.fromhex('c220ad181929f0004a4a4aaa'):raise FormatError('Unexpected dimension loader context.')
 from .expanded_content import Code
 c=Code();c.emit('bf40850b 8d2419 08 da ad1019 293f00 0a aa')
 c.emit('bf'+cpu_address(TABLE).to_bytes(3,'little').hex());c.branch(0xf0,'done');c.emit('8d2419');c.label('done');c.emit('fa 28 ad2419 6b')
 table=bytearray(128)
 for resource,(width,height) in p.map_sizes.items():table[resource*2:resource*2+2]=bytes((width,height))
 return [(pc(0x0b8507),b'\x22'+cpu_address(HOOK).to_bytes(3,'little'),'custom dimensions loader'),(HOOK,c.done(),'custom dimensions routine'),(TABLE,bytes(table),'custom layout dimensions')]
