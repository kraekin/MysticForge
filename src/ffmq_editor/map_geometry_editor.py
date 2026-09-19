"""Resize preview and guarded top-left anchored geometry edits."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QPainter,QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QComboBox,QLabel,QPushButton,QMessageBox
from .map_geometry import SIZES,blockers,resize,members
from .tile_previews import floor_choices,thumbnails
from .render import qimage
from .expanded_content_editor import commit

def open_resize(w):
 if not w.project.expanded:
  from .expansion_editor import show_expansion
  show_expansion(w);return
 area=w.area_id;p=w.project;attr=p.rom.attributes[p.rom.areas[area].attributes_id]
 d=QDialog(w);d.setWindowTitle('Resize map');d.resize(690,650);box=QVBoxLayout(d)
 title=QLabel(f'{p.rom.areas[area].name} · currently {attr.width} × {attr.height} tiles');box.addWidget(title)
 note=QLabel('Existing terrain stays at the top-left. Objects and entrances keep their coordinates. Resizing makes terrain independent when needed; setups sharing the exact same area record cannot be resized independently yet. Original maps can grow, or shrink back to their original size. Smaller crops are available for new maps.');note.setWordWrap(True);box.addWidget(note)
 form=QFormLayout();box.addLayout(form);width=QComboBox();height=QComboBox();floor=QComboBox();floor.setMaxVisibleItems(12)
 for value in SIZES:width.addItem(str(value),value);height.addItem(str(value),value)
 width.setCurrentIndex(width.findData(attr.width));height.setCurrentIndex(height.findData(attr.height));form.addRow('Width (tiles)',width);form.addRow('Height (tiles)',height);form.addRow('Fill added space with',floor)
 for n,icon,tip,transparent in floor_choices(w.renderer,p,area):
  floor.addItem(icon,f'Tile ${n:02X}'+(' · background shows through' if transparent else ''),n);floor.setItemData(floor.count()-1,tip,Qt.ItemDataRole.ToolTipRole)
 preview=QLabel();preview.setAlignment(Qt.AlignmentFlag.AlignCenter);preview.setMinimumHeight(260);box.addWidget(preview,1)
 status=QLabel();status.setWordWrap(True);box.addWidget(status)
 if area<108:
  warning=QLabel('Original events can contain hard-coded map coordinates or terrain addresses. Coordinates are preserved, but resized original maps still need in-game testing.');warning.setWordWrap(True);box.addWidget(warning)
 apply=QPushButton('Apply map size');box.addWidget(apply)
 rgba,atlas,props,state=w.renderer.area(p,area,set(),sprites=False);original=QPixmap.fromImage(qimage(rgba));tiles,_=thumbnails(w.renderer,p,area,atlas,state)
 def refresh():
  x,y=width.currentData(),height.currentData();problems=blockers(p,area,x,y)
  same=(x,y)==(attr.width,attr.height);removed=attr.width*attr.height-min(x,attr.width)*min(y,attr.height)
  status.setText(('\n'.join(problems[:6]) if problems else f'{x} × {y} tiles. '+(f'{removed} terrain cells will be cropped. ' if removed else 'No terrain cells cropped. ')+f'Affected area records: '+', '.join(f'${i:02X}' for i in members(p,area)))+'\n'+(floor.itemData(floor.currentIndex(),Qt.ItemDataRole.ToolTipRole) or ''))
  apply.setEnabled(not problems and not same and floor.currentData() is not None)
  image=QPixmap(x*16,y*16);image.fill(QColor('#27333c'));paint=QPainter(image)
  if floor.currentData() is not None:paint.drawTiledPixmap(image.rect(),QPixmap.fromImage(qimage(tiles[floor.currentData()])))
  paint.drawPixmap(0,0,original);paint.end();preview.setPixmap(image.scaled(560,300,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
 def apply_size():
  if w.project is not p or w.area_id!=area:w.error('The map changed. Reopen Resize map.');return
  x,y=width.currentData(),height.currentData();removed=attr.width*attr.height-min(x,attr.width)*min(y,attr.height)
  if removed and QMessageBox.question(d,'Crop terrain?',f'Remove {removed} terrain cells outside {x} × {y}? Objects and known arrivals have been checked. You can undo this change.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
  if commit(w,lambda:resize(p,area,x,y,floor.currentData()),'Resize map terrain'):w.selection.reset();d.accept();w.fit_views()
 for widget in (width,height,floor):widget.currentIndexChanged.connect(refresh)
 apply.clicked.connect(apply_size);refresh();w.resize_map_dialog=d;d.setModal(True);d.show()
