"""Create an empty independent field map using verified template settings."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QComboBox,QSpinBox,QPushButton
from .new_maps import create
from PySide6.QtGui import QIcon,QPixmap
from .render import qimage
import numpy as np
from .expanded_content_editor import commit

def open_new_map(w):
 if not w.project.expanded:
  from .expansion_editor import show_expansion
  show_expansion(w);return
 d=QDialog(w);d.setWindowTitle('New map');d.resize(600,410);box=QVBoxLayout(d)
 note=QLabel('Create a new area ID with independent terrain. The template supplies its dimensions, tileset, backgrounds and animation settings. The map starts with a floor tile and no objects, entrances or restoration scripts. Add those deliberately after designing it. Original maps remain intact.');note.setWordWrap(True);box.addWidget(note)
 form=QFormLayout();box.addLayout(form);name=QLineEdit('New map');form.addRow('Editor name',name);source=QComboBox()
 for a in w.rom.areas[:108]:
  if a.layout_id:source.addItem(f'{a.name} · area ${a.id:02X}',a.id)
 source.setCurrentIndex(max(0,source.findData(w.area_id)));form.addRow('Graphics and size template',source)
 floor=QComboBox();form.addRow('Starting floor tile',floor)
 def tiles():
  floor.clear();i=source.currentData();atlas,_,_=w.renderer.metatiles(w.project,i,set());props=np.frombuffer(w.project.fixed('properties',w.project.tileset(i)),dtype=np.uint8).reshape(128,2)
  for n in range(128):
   if not int(props[n,0])&7 and int(props[n,1])&0xe0!=0x80:floor.addItem(QIcon(QPixmap.fromImage(qimage(atlas[n]))),f'Tile ${n:02X}',n)
 source.currentIndexChanged.connect(tiles);tiles()
 hint=QLabel('The entry starts in the center. Choose this map in Add overworld location or as the destination in Add entrance. Build an exit before testing. Map names here are editor labels, not new in-game dialogue.');hint.setWordWrap(True);box.addWidget(hint)
 button=QPushButton('Create new map');box.addWidget(button)
 def apply():
  result=[]
  if floor.currentData() is None:w.error('This template has no verified ordinary floor tile.');return
  if commit(w,lambda:result.append(create(w.project,source.currentData(),name.text(),floor.currentData())),'Create new map'):
   d.accept();w.tool.setCurrentText('Pencil');w.select_area(result[0])
 button.clicked.connect(apply);w.new_map_dialog=d;d.setModal(True);d.show()
