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
 note=QLabel('Create a new area ID with independent terrain. Choose its size independently. The template supplies tileset, backgrounds and animation settings. The map starts with a floor tile and no objects, entrances or restoration scripts. Add those deliberately after designing it. Original maps remain intact.');note.setWordWrap(True);box.addWidget(note)
 form=QFormLayout();box.addLayout(form);name=QLineEdit('New map');form.addRow('Editor name',name);source=QComboBox()
 for a in w.rom.areas[:108]:
  if a.layout_id:source.addItem(f'{a.name} · area ${a.id:02X}',a.id)
 source.setCurrentIndex(max(0,source.findData(w.area_id)));form.addRow('Graphics template',source)
 from .map_geometry import SIZES
 width=QComboBox();height=QComboBox()
 for size in SIZES:width.addItem(str(size)+' tiles',size);height.addItem(str(size)+' tiles',size)
 form.addRow('Width',width);form.addRow('Height',height)
 floor=QComboBox();floor.setMaxVisibleItems(12);form.addRow('Starting floor tile',floor)
 floor_hint=QLabel();floor_hint.setWordWrap(True);box.addWidget(floor_hint)
 def floor_info():floor_hint.setText(floor.itemData(floor.currentIndex(),Qt.ItemDataRole.ToolTipRole) or '')
 from PySide6.QtCore import Qt
 floor.currentIndexChanged.connect(floor_info)
 def tiles():
  floor.clear();i=source.currentData();attrs=w.rom.attributes[w.rom.areas[i].attributes_id]
  width.setCurrentIndex(width.findData(attrs.width));height.setCurrentIndex(height.findData(attrs.height))
  from .tile_previews import floor_choices
  for n,icon,tip,transparent in floor_choices(w.renderer,w.project,i):
   floor.addItem(icon,f'Tile ${n:02X}'+(' · background shows through' if transparent else ''),n);floor.setItemData(floor.count()-1,tip,Qt.ItemDataRole.ToolTipRole)
  floor_info()
 source.currentIndexChanged.connect(tiles);tiles()
 hint=QLabel('The entry starts in the center. Choose this map in Add overworld location or as the destination in Add entrance. Build an exit before testing. Map names here are editor labels, not new in-game dialogue.');hint.setWordWrap(True);box.addWidget(hint)
 button=QPushButton('Create new map');box.addWidget(button)
 def apply():
  result=[]
  if floor.currentData() is None:w.error('This template has no verified ordinary floor tile.');return
  if commit(w,lambda:result.append(create(w.project,source.currentData(),name.text(),floor.currentData(),width.currentData(),height.currentData())),'Create new map'):
   d.accept();w.tool.setCurrentText('Pencil');w.select_area(result[0])
 button.clicked.connect(apply);w.new_map_dialog=d;d.setModal(True);d.show()
