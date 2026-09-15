"""New field areas with independent terrain and dedicated entry destinations."""
from copy import copy
from .rom import Area,pc,FormatError
from .expanded_content import destination_id
SELECTORS=0xf8400

def destination(p,resource):
 for i,c in p.newmaps.items():
  if destination_id(c['entry'])==resource:return bytes((i,c['y'],c['x']|(c['facing']<<6)))
 return None

def sync_catalog(p):
 signature=(tuple((i,repr(c)) for i,c in sorted(p.newmaps.items())),tuple((i,repr(c)) for i,c in sorted(p.sprite_sets.items())))
 if getattr(p.rom,'map_signature',None)==signature:return
 if not p.newmaps and not p.sprite_sets:
  if hasattr(p.rom,'map_signature'):p.rom=p.base_rom
  return
 r=copy(p.base_rom);r.base_rom=p.base_rom;r.map_signature=signature
 areas=list(r.areas)
 for i,c in sorted(p.newmaps.items()):
  if i!=len(areas) or not isinstance(c,dict):raise FormatError('New map IDs must be consecutive from 108')
  if not isinstance(c.get('source'),int) or not 1<=c['source']<108:raise FormatError('Invalid map template')
  source=r.areas[c['source']]
  if source.layout_id==0:raise FormatError('Choose a field-map template')
  header=bytearray(source.header);header[0]=(header[0]&192)|c['layout']
  areas.append(Area(i,0x120000+i*0x100,bytes(header),(),c['name']))
 from dataclasses import replace
 from .sprite_sets import COUNT
 r.sprite_descriptors={}
 for i,c in p.sprite_sets.items():
  if type(i) is not int or not 0<=i<len(areas):raise FormatError('Invalid sprite-set area')
  h=bytearray(areas[i].header);h[2]=COUNT+i;areas[i]=replace(areas[i],header=bytes(h));r.sprite_descriptors[COUNT+i]=c['data']
 r.areas=tuple(areas);r.area_actions=(*r.area_actions,*( () for _ in p.newmaps))
 r.object_capacities=dict(r.object_capacities);r.structural_object_sets=set(r.structural_object_sets)
 for a in areas[108:]:r.object_capacities[a.offset]=0;r.structural_object_sets.add(a.offset)
 p.rom=r

def validate(p):
 if len(p.newmaps)>8 or (p.newmaps and not p.expanded):raise FormatError('New maps require expansion; eight maps maximum')
 used=set()
 for i,c in p.newmaps.items():
  if set(c)!={'source','layout','name','entry','x','y','facing'}:raise FormatError('Invalid new map record')
  if not isinstance(c['name'],str) or not c['name'].strip() or len(c['name'])>80:raise FormatError('Map name must be 1–80 characters')
  if c['layout'] not in p.layout_copies or p.layout_bindings.get(i)!=c['layout']:raise FormatError('New map needs independent terrain')
  if type(c['entry']) is not int or not 0<=c['entry']<39 or c['entry'] in used or c['entry'] in p.content['entrances']:raise FormatError('New map destination slot collision')
  raw=p.fixed('destination',destination_id(c['entry']))
  if raw[0]!=i:raise FormatError('A new map entry must keep its own area; edit its arrival position instead')
  used.add(c['entry']);a=p.rom.attributes[p.rom.areas[i].attributes_id]
  if raw[1]>=a.height or (raw[2]&63)>=a.width:raise FormatError('New map arrival is outside its bounds')
  if any(type(c[k]) is not int for k in ('x','y','facing')) or not 0<=c['x']<a.width or not 0<=c['y']<a.height or not 0<=c['facing']<4:raise FormatError('Map entry coordinates invalid')

def create(p,source,name,fill):
 if not p.expanded:raise FormatError('Enable expanded ROM export first')
 if type(source) is not int or not 0<=source<108 or p.rom.areas[source].layout_id==0:raise FormatError('Choose a field-map template')
 if len(p.newmaps)>=8:raise FormatError('All eight new map slots are used')
 layout=next((j for j in range(44,64) if j not in p.layout_copies),None)
 used=set(p.content['entrances'])|{c['entry'] for c in p.newmaps.values()}
 entry=next((j for j in range(39) if j not in used),None)
 if layout is None or entry is None:raise FormatError('Independent terrain or entry destination slots are full')
 props=p.fixed('properties',p.tileset(source))
 if type(fill) is not int or not 0<=fill<128 or props[fill*2]&7 or props[fill*2+1]&0xe0==0x80:raise FormatError('Choose a floor tile with ordinary traversal and no entrance action')
 a=p.rom.areas[source];attrs=p.rom.attributes[a.attributes_id];i=108+len(p.newmaps)
 p.layout_copies[layout]={'source':a.layout_id,'cells':bytes((fill,))*(attrs.width*attrs.height)};p.layout_bindings[i]=layout
 p.newmaps[i]={'source':source,'layout':layout,'name':name.strip(),'entry':entry,'x':attrs.width//2,'y':attrs.height//2,'facing':0}
 if source in p.sprite_sets:
  from copy import deepcopy
  p.sprite_sets[i]=deepcopy(p.sprite_sets[source])
 sync_catalog(p)
 if p.tileset(source)>=16:
  from .expanded_content import copy_metatiles,KINDS
  private=copy_metatiles(p,i)
  for kind,(field,size) in KINDS.items():p.content['sets'][private][field]=p.fixed(kind,p.tileset(source))
 p.validate_expansion();return i

def writes(p):
 if not p.newmaps:return []
 from .expanded_content import coordinate_id
 for area in p.newmaps:
  attrs=p.rom.attributes[p.rom.areas[area].attributes_id];props=p.fixed('properties',p.tileset(area))
  linked={tuple(p.fixed('coordinate',coordinate_id(j))[:2]) for j,e in p.content['entrances'].items() if e['area']==area}
  for k,tile in enumerate(p.resource('layout',p.layout_id(area))):
   action=props[(tile&127)*2+1]
   if action&0xe0==0x80 and (action!=0x80 or (k%attrs.width,k//attrs.width) not in linked):raise FormatError(f"New map {p.rom.areas[area].name} has an unlinked or unsupported entrance tile at ({k%attrs.width}, {k//attrs.width}); use Add entrance with a normal door")
 # New maps have no inherited restoration scripts. Original selectors unchanged.
 selectors=p.rom.data[pc(0x06be77):pc(0x06be77)+108]+b'\x80'*(128-108)
 result=[(SELECTORS,selectors,'expanded map-state selectors')]
 for address in (0x01c840,0x01c8b2):
  at=pc(address)
  if p.rom.data[at:at+4]!=bytes.fromhex('bf77be06'):raise FormatError('Map-state selector guard failed')
  result.append((at,bytes.fromhex('bf00841f'),'map-state selector operand'))
 # New maps have no original coordinate lookup. The existing expanded override
 # handles their user-created doors and returns without scanning the vanilla table.
 return result
