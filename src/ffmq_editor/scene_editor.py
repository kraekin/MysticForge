"""Shared scene workspace for original event timelines and verified route editors."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QPainter,QPen,QColor,QPixmap
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QSplitter,QListWidget,QTabWidget,QSpinBox,QCheckBox,QPlainTextEdit,QMessageBox)
from .entrance_destination import ArrivalCanvas
from .render import qimage
from .scene_timeline import steps,walk_context
from .scene_commands import family,options
from .scene_registry import available
from .event_editing import change,replacement,tokens
from .expanded_content_editor import commit

class PathCanvas(ArrivalCanvas):
 def __init__(self):super().__init__();self.origin=None;self.endpoint=None
 def paintEvent(self,event):
  p=QPainter(self);p.fillRect(self.rect(),QColor('#182128'));s,x,y=self.transform();p.translate(x,y);p.scale(s,s);p.drawPixmap(0,0,self.pixmap)
  if self.origin is not None and self.endpoint is not None:
   p.setPen(QPen(QColor('#7bff80'),2));a,b=self.origin,self.endpoint
   p.drawLine(QPointF(a[0]*16+8,a[1]*16+8),QPointF(b[0]*16+8,b[1]*16+8));p.drawEllipse(QPointF(a[0]*16+8,a[1]*16+8),3,3)
   p.setPen(QPen(QColor('#ffff00'),1));p.drawRect(b[0]*16,b[1]*16,16,16)
  p.end()

class SceneWorkspace(QDialog):
 def __init__(self,w,entry=0x03f862,area=None,extent=None):
  super().__init__(w);self.window=w;self.project=w.project;self.entry=entry;self.extent=extent;self.history=[];self.loading=False;self.anchor=None;self.loaded_step=None
  self.setWindowTitle('MysticForge — Scene editor');self.resize(1250,880)
  self.scenes={s.entry:s for s in available(w.project.base_rom)}
  root=QVBoxLayout(self);bar=QHBoxLayout();root.addLayout(bar);self.scene=QComboBox()
  for scene in self.scenes.values():
   self.scene.addItem(scene.title,scene.entry);self.scene.setItemData(self.scene.count()-1,scene.note,Qt.ItemDataRole.ToolTipRole)
  if entry not in self.scenes:self.scene.addItem(f'Event ${entry:06X}',entry)
  self.scene.setCurrentIndex(self.scene.findData(entry));bar.addWidget(self.scene,1);self.back=QPushButton('Back to caller');bar.addWidget(self.back);self.back.clicked.connect(self.go_back)
  note=QLabel('Script order, not a playback: branches show possible paths and calls open their own sequence. Only verified edits are enabled. Paths are previews; collision and live actor positions are not simulated.');note.setWordWrap(True);root.addWidget(note)
  self.scene_note=QLabel();self.scene_note.setWordWrap(True);root.addWidget(self.scene_note)
  self.location=QLabel();root.addWidget(self.location)
  self.tabs=QTabWidget();root.addWidget(self.tabs,1);page=QWidget();self.tabs.addTab(page,'Timeline and map');box=QVBoxLayout(page)
  split=QSplitter();box.addWidget(split,1);left=QWidget();l=QVBoxLayout(left);split.addWidget(left);self.timeline=QListWidget();l.addWidget(self.timeline)
  self.follow=QPushButton('Open called event / branch');l.addWidget(self.follow);self.follow.clicked.connect(self.open_link)
  right=QWidget();r=QVBoxLayout(right);split.addWidget(right);split.setSizes([420,800])
  self.detail=QLabel();self.detail.setWordWrap(True);r.addWidget(self.detail);self.map=QComboBox()
  from .workspace_ui import version_name
  for a in w.rom.areas:self.map.addItem(f'{a.name} / {version_name(w,a.id)}',a.id)
  self.map.setCurrentIndex(self.map.findData(area if area is not None else self.scenes[entry].area if entry in self.scenes else w.area_id));r.addWidget(self.map)
  self.canvas=PathCanvas();r.addWidget(self.canvas,1)
  self.set_start=QCheckBox('Set preview starting position — click map (does not edit ROM)');r.addWidget(self.set_start)
  self.position=QLabel();self.position.setWordWrap(True);r.addWidget(self.position)
  controls=QHBoxLayout();r.addLayout(controls);self.direction=QComboBox();self.direction.addItems(['Up','Right','Down','Left']);self.distance=QSpinBox();self.distance.setRange(1,15)
  self.option_label=QLabel('Direction');controls.addWidget(self.option_label);controls.addWidget(self.direction);controls.addWidget(QLabel('Tiles'));controls.addWidget(self.distance)
  self.text=QPlainTextEdit();r.addWidget(self.text,1)
  from .dialogue_tokens import add_token_picker
  self.token_host=QWidget();tokenrow=QHBoxLayout(self.token_host);add_token_picker(tokenrow,self.text,w.project.base_rom);r.addWidget(self.token_host)
  self.status=QLabel();self.status.setWordWrap(True);r.addWidget(self.status)
  row=QHBoxLayout();r.addLayout(row);self.apply=QPushButton('Apply selected step');row.addWidget(self.apply);self.apply.clicked.connect(self.apply_step)
  reset=QPushButton('Discard typing');row.addWidget(reset);reset.clicked.connect(self.discard)
  self.advanced=QPushButton('Dialogue / other parameters…');row.addWidget(self.advanced);self.advanced.clicked.connect(self.edit_parameters)
  self.route=None
  if w.project.expanded and len(w.project.objects(16))>=6:
   from .story_scene_editor import SceneEditor
   self.route=SceneEditor(w);self.route.embedded=True;self.route.setParent(self.tabs);self.route.setWindowFlags(Qt.WindowType.Widget);self.tabs.addTab(self.route,'Kaeli: axe and actor routes')
   for button in self.route.findChildren(QPushButton):
    if button.text()=='Close':button.hide()
  close=QPushButton('Close');root.addWidget(close);close.clicked.connect(self.close)
  self.scene.currentIndexChanged.connect(self.change_scene);self.timeline.currentRowChanged.connect(self.select);self.map.currentIndexChanged.connect(self.render_map);self.canvas.clicked.connect(self.pick)
  self.direction.currentIndexChanged.connect(self.update_path);self.distance.valueChanged.connect(self.update_path);self.text.textChanged.connect(self.update_path)
  self.render_map();self.rebuild()
 def current(self):
  n=self.timeline.currentRow();return self.items[n] if 0<=n<len(self.items) else None
 def rebuild(self):
  old=self.timeline.currentRow();self.loading=True;self.items=steps(self.project,self.entry,self.extent);self.timeline.clear()
  for step in self.items:
   editable=step.segment and (step.segment.kind=='text' or step.pair is not None and family(step.segment.raw[step.pair+1],step.segment.raw[step.pair]))
   self.timeline.addItem(('[Edit] ' if editable else '• ')+step.label.replace('\n',' / '));self.timeline.item(self.timeline.count()-1).setToolTip(f'${step.address:06X}\n'+step.label)
  self.scene_note.setText((self.scenes[self.scene.currentData()].note if self.scene.currentData() in self.scenes else 'Event opened from the browser.')+' Map selection is a preview; runtime object slots are not automatically mapped to stored objects.')
  self.location.setText(' → '.join([self.scenes[at].title if at in self.scenes else f'Event ${at:06X}' for at in [at for at,_ in self.history]+[self.entry]])+f' · ${self.entry:06X} · branches listed in script address order')
  self.back.setEnabled(bool(self.history));self.loading=False;self.timeline.setCurrentRow(min(max(old,0),len(self.items)-1));self.select()
 def dirty(self):
  step=self.loaded_step
  if step is None or step.segment is None:return False
  saved=self.project.event_edits.get(step.address,{}).get('value')
  if step.segment.kind=='text':return self.text.toPlainText()!=(saved if saved is not None else tokens(self.project.base_rom,step.segment.raw))
  return bool(self.f and self.raw!=list(saved if saved is not None else step.segment.raw))
 def allow_leave(self):
  if not self.dirty():return True
  answer=QMessageBox.question(self,'Unapplied scene edit','Apply the selected step before leaving it?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
  if answer==QMessageBox.StandardButton.Cancel:return False
  if answer==QMessageBox.StandardButton.Save:
   step=self.loaded_step;value=list(self.raw) if self.f else self.text.toPlainText()
   if not commit(self.window,lambda:change(self.project,step.address,value),'Edit scene step'):return False
  return True
 def discard(self):self.loaded_step=None;self.select()
 def allow_route_leave(self):
  if self.route is None:return True
  from copy import deepcopy
  from . import story_scenes as scene
  saved=deepcopy(self.project.story_scene or scene.defaults(self.project));saved.setdefault('mother',deepcopy(scene.MOTHER_ROUTE))
  if self.route.record==saved:return True
  answer=QMessageBox.question(self,'Unapplied actor routes','Apply the Kaeli actor routes before closing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
  if answer==QMessageBox.StandardButton.Cancel:return False
  if answer==QMessageBox.StandardButton.Save:return commit(self.window,lambda:scene.apply(self.project,self.route.record),'Edit Kaeli actor routes')
  return True
 def closeEvent(self,event):
  if self.allow_leave() and self.allow_route_leave():event.accept()
  else:event.ignore()
 def reject(self):
  if self.allow_leave() and self.allow_route_leave():super().reject()
 def change_scene(self):
  if not self.allow_leave():
   self.scene.blockSignals(True);self.scene.setCurrentIndex(self.scene.findData(self.entry));self.scene.blockSignals(False);return
  self.loaded_step=None
  self.entry=self.scene.currentData();self.extent=None;self.anchor=None;self.history=[]
  if self.entry in self.scenes:self.map.setCurrentIndex(self.map.findData(self.scenes[self.entry].area))
  self.rebuild()
 def render_map(self):
  area=self.map.currentData()
  if area is None:return
  image=self.window.renderer.area(self.project,area,self.project.flags)[0];self.canvas.pixmap=QPixmap.fromImage(qimage(image));self.anchor=None
  self.canvas.origin=None;self.canvas.endpoint=None;self.canvas.update()
  if hasattr(self,'items'):self.select()
 def select(self,*_):
  if self.loading:return
  if not self.allow_leave():
   if self.loaded_step in self.items:
    self.timeline.blockSignals(True);self.timeline.setCurrentRow(self.items.index(self.loaded_step));self.timeline.blockSignals(False)
   return
  self.loading=True;step=self.current();self.loaded_step=step;self.anchor=None;self.set_start.setChecked(False);self.raw=None;self.f=None
  if step:
   self.detail.setText(step.label);s=step.segment
   if s and s.kind=='field' and step.pair is not None:
    self.raw=list(self.project.event_edits.get(s.address,{}).get('value',s.raw));i=step.pair;self.f=family(s.raw[i+1],s.raw[i])
    if self.f:
     self.direction.clear()
     for ident,label in options(self.f,s.raw[i]):self.direction.addItem(label,ident)
     self.option_label.setText('Audio' if self.f[0]=='audio' else 'Direction')
     self.direction.setCurrentIndex(self.direction.findData(self.raw[i] if self.f[0]=='audio' else self.raw[i+1]-self.f[1] if self.f[0]=='walk' else self.raw[i]>>4));self.distance.setValue(max(1,self.raw[i]>>4))
   istext=bool(s and s.kind=='text')
   if istext:self.text.setPlainText(self.project.event_edits.get(s.address,{}).get('value',tokens(self.project.base_rom,s.raw)))
  else:self.detail.setText('No steps');istext=False
  self.text.setVisible(istext);self.token_host.setVisible(istext);self.canvas.setVisible(not istext);self.map.setVisible(not istext)
  self.direction.setEnabled(bool(self.f));self.distance.setEnabled(bool(self.f and self.f[0]=='walk'));self.set_start.setVisible(bool(self.f and self.f[0]=='walk'))
  self.follow.setEnabled(bool(step and step.links));self.loading=False;self.update_path()
 def origin(self):
  if self.anchor:return self.anchor,'User-set preview position; not a verified runtime position.'
  step=self.current();context=walk_context(self.project,step) if step else None
  if context and context[0]==self.map.currentData():return context[1],'Start derived from a direct transition and preceding walks in this group.'
  return None,'Runtime starting position is unknown here. Set a preview start to draw this relative movement.'
 def update_path(self,*_):
  if self.loading:return
  step=self.current();self.canvas.origin=None;self.canvas.endpoint=None;self.apply.setEnabled(False)
  if not step:return
  try:
   if self.f and self.f[0]=='audio':
    self.raw[step.pair]=self.direction.currentData();replacement(self.project,step.segment,self.raw)
    self.position.setText('Audio selection; no actor path is changed.')
    self.apply.setEnabled(self.raw!=list(self.project.event_edits.get(step.address,{}).get('value',step.segment.raw)))
    self.status.setText('Choose a verified sound effect or music ID. The original command, sequence order and byte length are preserved.')
   elif self.f:
    i=step.pair;self.raw[i]=(self.distance.value() if self.f[0]=='walk' else self.direction.currentIndex())*16+(step.segment.raw[i]&15);self.raw[i+1]=self.f[1]+self.direction.currentIndex() if self.f[0]=='walk' else self.f[1]
    replacement(self.project,step.segment,self.raw)
    start,note=self.origin();self.position.setText(note)
    if start and self.f[0]=='walk':
     dx,dy=((0,-1),(1,0),(0,1),(-1,0))[self.direction.currentIndex()];end=(start[0]+dx*self.distance.value(),start[1]+dy*self.distance.value());self.canvas.origin=start;self.canvas.endpoint=end;self.canvas.point=end
    self.apply.setEnabled(self.raw!=list(self.project.event_edits.get(step.address,{}).get('value',step.segment.raw)))
    self.status.setText('Click a destination on the same row or column as the start (1–15 tiles), or use the controls. Original scene order and actor slot stay fixed.')
   elif step.segment and step.segment.kind=='text':
    replacement(self.project,step.segment,self.text.toPlainText());self.apply.setEnabled(self.text.toPlainText()!=self.project.event_edits.get(step.address,{}).get('value',tokens(self.project.base_rom,step.segment.raw)));self.status.setText('Shared dialogue: text must fit its original protected span.')
   else:self.position.setText('');self.status.setText('Protected step. Calls, battle commands, branches and unknown operations stay unchanged. Follow a link to inspect another routine.')
  except ValueError as e:self.status.setText(str(e))
  self.canvas.update()
 def pick(self,x,y):
  if not self.f or self.f[0]!='walk':return
  if self.set_start.isChecked():self.anchor=(x,y);self.set_start.setChecked(False);self.update_path();return
  start,_=self.origin()
  if start is None:self.status.setText('Choose Set preview starting position first.');return
  dx,dy=x-start[0],y-start[1];distance=abs(dx)+abs(dy)
  if dx and dy or not 1<=distance<=15:self.status.setText('Choose a square 1–15 tiles away on the same row or column.');return
  self.loading=True;self.direction.setCurrentIndex(1 if dx>0 else 3 if dx<0 else 2 if dy>0 else 0);self.distance.setValue(distance);self.loading=False;self.update_path()
 def apply_step(self):
  if self.window.project is not self.project:self.window.error('The project changed; reopen Scene editor.');return
  step=self.current()
  if not step or not step.segment:return
  value=list(self.raw) if self.f else self.text.toPlainText()
  if commit(self.window,lambda:change(self.project,step.address,value),'Edit scene step'):self.rebuild()
 def open_link(self):
  if not self.allow_leave():return
  self.loaded_step=None
  step=self.current()
  if not step or not step.links:return
  if len(step.links)>1:
   from PySide6.QtWidgets import QInputDialog
   choices=[f'{kind} → ${at:06X}' for kind,at in step.links];choice,ok=QInputDialog.getItem(self,'Choose path','Both paths are possible; no condition is executed.',choices,0,False)
   if not ok:return
   kind,target=step.links[choices.index(choice)]
  else:kind,target=step.links[0]
  from .events import fragments
  length=step.link_extent if kind=='bounded' else dict(fragments(self.project.base_rom)).get(target)
  self.history.append((self.entry,self.extent));self.entry=target;self.extent=length;self.rebuild()
 def go_back(self):
  if not self.allow_leave():return
  self.loaded_step=None
  if self.history:self.entry,self.extent=self.history.pop();self.rebuild()
 def edit_parameters(self):
  if not self.allow_leave():return
  self.loaded_step=None
  from .event_editor import show_editor
  step=self.current();show_editor(self.window,self.entry,self.extent,step.address if step else None);self.rebuild()

def open_workspace(w,entry=0x03f862,area=None,extent=None):
 d=SceneWorkspace(w,entry,area,extent);w.scene_workspace=d;d.setModal(True);d.show();return d
