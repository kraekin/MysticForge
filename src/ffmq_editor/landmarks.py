"""Overworld landmark OBJ pieces, separate from terrain and route nodes."""
from .rom import pc,FormatError
START=0xfc000
BASE=0x3eb44
COUNT=143
LOADS=(0x01e6b1,0x01e6c0,0x01e6cd,0x01e70c,0x01e712)
def records(p):return tuple(p.landmarks) if p.landmarks is not None else tuple(p.rom.data[BASE+i*5:BASE+i*5+5] for i in range(COUNT))
def validate(p):
 if p.landmarks is None:return
 if not isinstance(p.landmarks,list) or len(p.landmarks)>256:raise FormatError('At most 256 landmark pieces are supported')
 if len(p.landmarks)>COUNT and not p.expanded:raise FormatError('Additional landmark pieces require 1 MiB expansion')
 for r in p.landmarks:
  if not isinstance(r,bytes) or len(r)!=5 or r[0]>=48 or r[1]>=64:raise FormatError('Invalid landmark piece')
 # Conservative: count every visibility state together in each 19 by 13 viewport.
 counts=[[0]*82 for _ in range(60)]
 for y,x,flag,tile,attr in p.landmarks:
  for top in range(max(-12,y-12),min(47,y)+1):
   for left in range(max(-18,x-18),min(63,x)+1):
    counts[top+12][left+18]+=1
    if counts[top+12][left+18]>64:raise FormatError('Too many landmark pieces in one screen region (64 maximum, counting all states)')
def writes(p):
 validate(p)
 if p.landmarks is None:return []
 raw=b''.join(p.landmarks)+b'\xff'
 if len(p.landmarks)<=COUNT:return [(BASE,raw,'overworld landmark pieces')]
 result=[(START,raw,'expanded overworld landmark pieces')]
 # This routine's other DB-relative accesses are low WRAM mirrors. Its mask
 # table is a long bank-01 read; its helper clears WRAM sprite slots only.
 address=pc(0x01e635)
 if p.rom.data[address:address+2]!=b'\xa9\x07':raise FormatError('Landmark data-bank guard failed')
 result.append((address,b'\xa9\x1f','landmark data bank'))
 for i,a in enumerate(LOADS):
  at=pc(a);old=b'\xbd'+(0xeb44+i).to_bytes(2,'little')
  if p.rom.data[at:at+3]!=old:raise FormatError('Landmark table guard failed')
  result.append((at,b'\xbd'+(0xc000+i).to_bytes(2,'little'),'landmark table field'))
 return result
