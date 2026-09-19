"""Tile thumbnails that distinguish transparency from missing artwork."""
import numpy as np
from .rom import pc
from .render import color_rgb,qimage

def thumbnails(renderer,project,area,atlas,state):
 # Use one representative sample only for simple repeating background layers.
 # Displaced copies and large composed scenes need coordinates: show a checker.
 yy,xx=np.indices((16,16));shade=np.where(((xx//4+yy//4)%2)[...,None],105,70)
 checker=np.empty((16,16,4),dtype=np.uint8);checker[:,:,:3]=shade;checker[:,:,3]=255
 background=checker;description='Transparent — reveals the background at this map position'
 a=project.rom.areas[area];index=((a.header[5]&224)>>2)|((a.header[6]&224)>>5)
 if index:
  mode=project.rom.data[pc(0x0b844f)+(index-1)*4]
  if mode&7 in (3,4,5,7) and (mode>>4)&7 not in (2,4,5,6):
   bg,_=renderer.background(area,state.flags,atlas,np.zeros((1,1),dtype=np.uint8))
   if bg is not None:
    background=bg.copy();background[background[:,:,3]==0,:3]=color_rgb(project.palette(state.palette)[0]);background[:,:,3]=255
    description='Transparent — shows this repeating background (position/animation may change its appearance)'
 elif not index:
  background=checker.copy();background[:,:,:3]=color_rgb(project.palette(state.palette)[0]);description='Transparent — shows the map backdrop color'
 result=atlas.copy();empty=result[:,:,:,3]==0
 result[empty]=np.broadcast_to(background,result.shape)[empty]
 return result,description

def tile_icon(pixels,transparent,entrance):
 from PySide6.QtCore import Qt
 from PySide6.QtGui import QIcon,QPixmap,QPainter,QColor
 pix=QPixmap.fromImage(qimage(pixels)).scaled(32,32,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
 if transparent or entrance:
  painter=QPainter(pix);painter.fillRect(0,21,32,11,QColor('#16333e'));painter.setPen(QColor('#ffffff'))
  font=painter.font();font.setPixelSize(9);font.setBold(True);painter.setFont(font);painter.drawText(1,30,'DOOR' if entrance else 'BG');painter.end()
 return QIcon(pix)

def description(index,props,transparent,background):
 entry=int(props[1])&0xe0==0x80
 movement='Blocks ordinary walking' if int(props[0])&7==7 else f'Movement class {int(props[0])&7}'
 return f'Tile ${index:02X} · '+('Entrance / transition trigger. ' if entry else '')+(background+'. ' if transparent else '')+movement+f'. Properties {int(props[0]):02X} {int(props[1]):02X}.'

def floor_choices(renderer,project,area):
 atlas,props,state=renderer.metatiles(project,area,set())
 previews,bg=thumbnails(renderer,project,area,atlas,state);seen=set();result=[]
 for n in range(128):
  if int(props[n,0])&7 or int(props[n,1])&0xe0==0x80:continue
  # Equivalent starting-floor choices add no useful information; retain every
  # tile in the main palette, but deduplicate exact artwork+behavior here.
  key=(atlas[n].tobytes(),props[n].tobytes())
  if key in seen:continue
  seen.add(key);transparent=bool(np.any(atlas[n,:,:,3]==0))
  result.append((n,tile_icon(previews[n],transparent,False),description(n,props[n],transparent,bg),transparent))
 return result
