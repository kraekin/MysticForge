"""Modeless palette for placing the game's landmark sprite pieces."""
from .event_flags import flag_label
import numpy as np
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import QWidget,QTabWidget,QComboBox,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QSpinBox,QFormLayout,QPushButton
from .landmarks import records,COUNT,BASE
from .expanded_content_editor import commit
from .render import qimage
from .world import position

class LandmarkEditor(QWidget):
 def __init__(self,w):
  super().__init__(w);self.w=w;self.drag_index=None;self.drop=None;self.setWindowTitle('Overworld artwork')
  box=QVBoxLayout(self);note=QLabel('Choose artwork below, then click the map to place it. Select / move lets you click and drag existing artwork. Right-click picks an existing piece. Escape cancels the preview. Artwork does not move routes or entrances.');note.setWordWrap(True);box.addWidget(note)
  self.mode=QComboBox();self.mode.addItems(["Paint artwork","Select / move"]);box.addWidget(self.mode)
  tabs=QTabWidget();box.addWidget(tabs,1);self.palette=QListWidget();self.palette.setViewMode(QListWidget.ViewMode.IconMode);self.palette.setIconSize(QSize(48,48));self.palette.setGridSize(QSize(78,76));tabs.addTab(self.palette,"Palette")
  self.palette.setResizeMode(QListWidget.ResizeMode.Adjust);self.palette.setMovement(QListWidget.Movement.Static);self.palette.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
  self.pieces=QListWidget();self.pieces.setIconSize(QSize(32,32));tabs.addTab(self.pieces,"Placed artwork")
  self.assets=sorted({(r[3],r[4]) for r in (*records(w.project),*(w.rom.data[BASE+i*5:BASE+i*5+5] for i in range(COUNT)))});self.icons={}
  tiles,colors=w.renderer.sprites.world_set()
  for tile,attr in self.assets:
   rgba=np.zeros((16,16,4),dtype=np.uint8);base=tile+((attr&1)<<8)
   for q in range(4):
    dx,dy=q%2,q//2;sx=1-dx if attr&64 else dx;sy=1-dy if attr&128 else dy
    pixels=tiles[(base+sx+sy*16)&511]
    if attr&64:pixels=pixels[:,::-1]
    if attr&128:pixels=pixels[::-1,:]
    w.renderer.sprites.paint_tile(rgba,pixels,colors[(attr>>1)&7],dx*8,dy*8)
   icon=QIcon(QPixmap.fromImage(qimage(rgba)).scaled(48,48));self.icons[tile,attr]=icon
   item=QListWidgetItem(icon,f'{tile:02X} / {attr:02X}');item.setToolTip(f'Sprite tile ${tile:02X}, attributes ${attr:02X}');self.palette.addItem(item)
  advanced=QWidget();form=QFormLayout(advanced);toggle=QPushButton("Precise coordinates / visibility…");toggle.setCheckable(True);toggle.toggled.connect(advanced.setVisible);box.addWidget(toggle);box.addWidget(advanced);advanced.hide();self.x=QSpinBox();self.x.setRange(0,63);self.y=QSpinBox();self.y.setRange(0,47);self.flag=QSpinBox();self.flag.setRange(0,255);self.flag.setDisplayIntegerBase(16);self.flag.setPrefix('$')
  for label,field in [('X',self.x),('Y',self.y),('Visibility flag',self.flag)]:form.addRow(label,field)
  buttons=QVBoxLayout();form.addRow(buttons)
  for text,callback in [('Coordinates from selected route node',self.at_node),('Place artwork',self.place),('Update selected piece',self.update_piece),('Remove selected piece',self.remove_piece)]:
   b=QPushButton(text);b.clicked.connect(callback);buttons.addWidget(b)
  self.feedback=QLabel();self.feedback.setWordWrap(True);box.addWidget(self.feedback)
  self.palette.itemClicked.connect(lambda *_:self.mode.setCurrentIndex(0));self.pieces.itemClicked.connect(lambda *_:self.mode.setCurrentIndex(1))
  self.pieces.currentRowChanged.connect(self.selected);self.palette.setCurrentRow(0);self.refresh();self.at_node()
  w.stack.indexChanged.connect(self.refresh)
 def refresh(self,*_):
  before=self.pieces.currentRow();self.pieces.blockSignals(True);self.pieces.clear()
  for i,(y,x,flag,tile,attr) in enumerate(records(self.w.project)):
   self.pieces.addItem(QListWidgetItem(self.icons.get((tile,attr),QIcon()),f'{i+1} · ({x}, {y}) · '+('Always visible' if not flag else flag_label(flag))))
  self.pieces.setCurrentRow(min(before,self.pieces.count()-1));self.pieces.blockSignals(False)
  self.feedback.setText(f'{self.pieces.count()} pieces. Additional pieces require expanded export. No screen region may contain more than 64 pieces, counting all states.')
 def selected(self,i):
  if i<0:return
  y,x,flag,tile,attr=records(self.w.project)[i];self.x.setValue(x);self.y.setValue(y);self.flag.setValue(flag)
  self.palette.setCurrentRow(self.assets.index((tile,attr)))
 def at_node(self):
  x,y=position(self.w.project,self.w.world_editor.node.value());self.x.setValue(x);self.y.setValue(y)
  self.feedback.setText(f"Using route node ${self.w.world_editor.node.value():02X} at ({x}, {y}). Click a node with Routes to select it, or paint directly with Artwork.")
 def raw(self):
  tile,attr=self.assets[self.palette.currentRow()];return bytes((self.y.value(),self.x.value(),self.flag.value(),tile,attr))
 def apply_records(self,rows,label):
  if commit(self.w,lambda:setattr(self.w.project,'landmarks',rows),label):self.refresh()
 def place(self):
  rows=list(records(self.w.project))
  if len(rows)>=COUNT and not self.w.project.expanded:
   self.feedback.setText('Enable 1 MiB export in File → ROM expansion to add more pieces.');return
  rows.append(self.raw());self.apply_records(rows,'Place overworld artwork')
 def update_piece(self):
  i=self.pieces.currentRow()
  if i<0:return
  rows=list(records(self.w.project));rows[i]=self.raw();self.apply_records(rows,'Update overworld artwork')
 def remove_piece(self):
  i=self.pieces.currentRow()
  if i<0:return
  rows=list(records(self.w.project));rows.pop(i);self.apply_records(rows,'Remove overworld artwork')

 def hover_map(self,x,y):
  self.w.canvas.art_preview=None
  if self.w.rom.areas[self.w.area_id].layout_id==0 and 0<=x<64 and 0<=y<48 and (self.mode.currentIndex()==0 or self.drag_index is not None):
   self.w.canvas.art_preview=(x,y,self.icons[self.assets[self.palette.currentRow()]].pixmap(16,16))
  self.w.canvas.viewport().update()
 def press_map(self,x,y,pick):
  hits=[i for i,r in enumerate(records(self.w.project)) if (r[1],r[0])==(x,y) and (not r[2] or r[2] in self.w.project.flags or self.w.hidden_sprites.isChecked())]
  if pick or self.mode.currentIndex()==1:
   if hits:
    self.pieces.setCurrentRow(hits[-1]);self.selected(hits[-1])
    if pick:self.mode.setCurrentIndex(0)
    else:self.drag_index=hits[-1];self.drop=(x,y)
   return
  self.x.setValue(x);self.y.setValue(y)
  if self.raw() not in records(self.w.project):self.place()
 def move_map(self,x,y):
  if self.drag_index is not None and 0<=x<64 and 0<=y<48:self.drop=(x,y)
  self.hover_map(x,y)
 def finish_map(self):
  i=self.drag_index;self.drag_index=None
  if i is not None and self.drop is not None:
   rows=list(records(self.w.project));r=bytearray(rows[i]);r[1],r[0]=self.drop
   if bytes(r)!=rows[i]:rows[i]=bytes(r);self.apply_records(rows,'Move overworld artwork')
  self.w.canvas.art_preview=None;self.w.canvas.viewport().update()

def open_landmarks(w):
 if not hasattr(w,'landmark_editor'):
  w.landmark_editor=LandmarkEditor(w)
  w.panel_stack.addWidget(w.landmark_editor);w.panel_selector.addItem('Artwork')
 w.landmark_editor.refresh()
 if w.tool.currentText()!='Artwork':w.tool.setCurrentText('Artwork')
 w.show_panel('Artwork')

