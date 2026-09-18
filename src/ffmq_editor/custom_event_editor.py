"""Ordered action tree for custom NPC events, with local undo and project apply."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem,QComboBox,QPlainTextEdit,QSpinBox,QFormLayout,QMessageBox,QDialogButtonBox)
from .custom_events import compile_actions,text_calls,label,branches,MUSIC_IDS,SOUND_IDS
from .private_dialogue import assign_record,plan,DATA,END
from .layout_storage import cpu_address

ROLE=Qt.ItemDataRole.UserRole
KINDS=[('say','Say something'),('choice','Ask a Yes / No question'),('give_item','Give an item / spell / equipment'),('music','Play music'),('sound','Play a sound effect'),('screen','Screen effect'),('if_flag','Check a game flag'),('set_flag','Set a game flag'),('clear_flag','Clear a game flag'),('wait','Wait'),('call_text','Show existing NPC dialogue'),('face_player','Turn the hero'),('end','End conversation')]

class ActionDialog(QDialog):
 def __init__(self,parent,kind,node=None):
  super().__init__(parent);self.kind=kind;self.node=deepcopy(node);self.setWindowTitle('Edit action' if node else 'Add action');self.resize(700,430)
  box=QVBoxLayout(self);box.addWidget(QLabel(dict(KINDS)[kind]));form=QFormLayout();box.addLayout(form)
  self.text=QPlainTextEdit();self.flag=QComboBox();self.frames=QSpinBox();self.call=QComboBox()
  from .event_flags import flag_label
  self.flag.addItem('Choose a game flag…',None)
  for i in range(256):self.flag.addItem(flag_label(i),i)
  if kind=='say':
   self.speaker=QComboBox();self.speaker.addItem('This NPC',('npc',));self.speaker.addItem('Hero / player reply',('hero',))
   from .custom_events import speaker_reference
   for i,obj in enumerate(parent.project.objects(parent.area)):
    if i==parent.index:continue
    try:speaker_reference(parent.project,parent.area,i)
    except ValueError:continue
    self.speaker.addItem(f'Other NPC: object ${i:02X}, sprite ${obj[6]&127:02X} at ({obj[3]&63}, {obj[2]&63})',('object',parent.area,i))
   selected=(node.get('speaker','npc'),) if node else ('npc',)
   if selected==('object',):selected=('object',node['speaker_area'],node['speaker_object'])
   found=next((i for i in range(self.speaker.count()) if tuple(self.speaker.itemData(i))==selected),-1)
   if found<0:self.speaker.addItem('Saved speaker (unavailable — choose another)',selected);found=self.speaker.count()-1
   self.speaker.setCurrentIndex(found);form.addRow('Who speaks?',self.speaker)
   hint=QLabel('Hero replies use the alternate game window. Other NPCs must be present on this map during play. This selects the speech position; it does not add a name label.');hint.setWordWrap(True);box.addWidget(hint)
   form.addRow('Dialogue',self.text);self.text.setPlainText(node['text'] if node else '')
   box.addWidget(QLabel('Enter adds a line break. Each Say action opens and closes a message.'))
   from .dialogue_tokens import add_token_picker,preview_text as resolve_preview,wrap_text as wrap_tokens
   token_row=QHBoxLayout();box.addLayout(token_row);self.token,self.insert_token=add_token_picker(token_row,self.text,parent.project.base_rom)
   tools=QHBoxLayout();box.addLayout(tools);wrap=QPushButton('Wrap lines');preview=QPushButton('Preview message…');tools.addWidget(wrap);tools.addWidget(preview)
   def wrap_text():
    self.text.setPlainText(wrap_tokens(parent.project.base_rom,self.text.toPlainText()))
   def preview_text():
    from .dialogue_preview import DialoguePreview
    self.preview=DialoguePreview(self,resolve_preview(parent.project.base_rom,self.text.toPlainText()));self.preview.show()
   wrap.clicked.connect(wrap_text);preview.clicked.connect(preview_text)
  elif kind=='choice':
   form.addRow('Question',self.text);self.text.setPlainText(node['text'] if node else '')
   from .dialogue_tokens import add_token_picker
   tokens=QHBoxLayout();box.addLayout(tokens);self.token,self.insert_token=add_token_picker(tokens,self.text,parent.project.base_rom)
   note=QLabel('The NPC asks this question, then the hero chooses Yes or No. Cancel also follows No. Add the response steps beneath each branch in the event tree.');note.setWordWrap(True);box.addWidget(note)
  elif kind=='give_item':
   from .events import inline_name
   from .event_editing import event_rom
   rom=event_rom(parent.project);self.item=QComboBox();self.quantity=QSpinBox()
   for ident in range(64):self.item.addItem(f'{inline_name(rom,0x1e,ident)} (${ident:02X})',ident)
   self.item.setCurrentIndex(node['item'] if node else 16)
   def quantity_limit():self.quantity.setRange(1,99 if self.item.currentData() in range(16,20) else 1)
   self.item.currentIndexChanged.connect(quantity_limit);quantity_limit();self.quantity.setValue(node['quantity'] if node else 1)
   form.addRow('Reward',self.item);form.addRow('Quantity (up to)',self.quantity)
   note=QLabel('Consumables stop at 99: a partial grant follows Received; an already full stack follows Cannot carry. Equipment and spells use the game’s normal grant behavior. Add a Say step for the reward message. For a one-time gift, check a flag first and set it only in Received. Key items alone do not run their original quest scripts.');note.setWordWrap(True);box.addWidget(note)
  elif kind in ('music','sound'):
   self.audio=QComboBox()
   for ident in (MUSIC_IDS if kind=='music' else SOUND_IDS):self.audio.addItem(f"{'Music track' if kind=='music' else 'Sound effect'} ${ident:02X}",ident)
   if node:self.audio.setCurrentIndex(self.audio.findData(node['id']))
   form.addRow('Audio',self.audio)
   note=QLabel('These IDs are used in original field events. Audio plays in the game, not in this dialog. Music continues after the conversation; select another music step to change it again.');note.setWordWrap(True);box.addWidget(note)
  elif kind=='screen':
   self.effect=QComboBox();self.effect.addItem('Shake horizontally','shake');self.effect.addItem('Fade to black, pause briefly, then fade back in','fade')
   if node:self.effect.setCurrentIndex(self.effect.findData(node['effect']))
   form.addRow('Effect',self.effect)
   note=QLabel('Effects finish before the next step. The paired fade always restores brightness.');note.setWordWrap(True);box.addWidget(note)
  elif kind=='face_player':
   self.direction=QComboBox();self.direction.addItems(['Up','Right','Down','Left']);self.direction.setCurrentIndex(node['direction'] if node else 0);form.addRow('Face',self.direction)
  elif kind=='end':
   note=QLabel('Return from this NPC event immediately. In a condition, this skips all remaining steps, including those after the condition.');note.setWordWrap(True);box.addWidget(note)
  elif kind=='wait':
   self.frames.setRange(1,255);self.frames.setValue(node['frames'] if node else 30);form.addRow('Frames',self.frames)
  elif kind=='call_text':
   for ident,(_,text) in text_calls(parent.project).items():self.call.addItem(f'NPC ${ident:02X}: '+text.replace('\n',' / ')[:90],ident)
   if node:self.call.setCurrentIndex(self.call.findData(node['npc']))
   form.addRow('Existing conversation',self.call);note=QLabel('Only verified text-only routines are listed. Their existing shared dialogue edits also apply. Complex quest events cannot be called here yet.');note.setWordWrap(True);box.addWidget(note)
  else:
   form.addRow('Game flag',self.flag);self.flag.setCurrentIndex(self.flag.findData(node['flag']) if node else 0)
   if kind=='if_flag':
    self.condition=QComboBox();self.condition.addItem('Is set',True);self.condition.addItem('Is clear',False);self.condition.setCurrentIndex(0 if not node or node.get('is_set',True) else 1);form.addRow('Condition',self.condition)
   note=QLabel('Flags are shared game state. Choose deliberately: changing an existing story flag can affect other maps and quests. An unnamed flag is not proof that it is unused.');note.setWordWrap(True);box.addWidget(note)
  self.error=QLabel();self.error.setWordWrap(True);box.addWidget(self.error)
  buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);box.addWidget(buttons);buttons.accepted.connect(self.accept_checked);buttons.rejected.connect(self.reject)
 def value(self):
  k=self.kind;n={'kind':k}
  if k=='say':
   n['text']=self.text.toPlainText();speaker=self.speaker.currentData();n['speaker']=speaker[0]
   if speaker[0]=='object':n.update(speaker_area=speaker[1],speaker_object=speaker[2])
  elif k=='choice':n['text']=self.text.toPlainText()
  elif k=='give_item':n.update(item=self.item.currentData(),quantity=self.quantity.value())
  elif k in ('music','sound'):n['id']=self.audio.currentData()
  elif k=='screen':n['effect']=self.effect.currentData()
  elif k=='face_player':n['direction']=self.direction.currentIndex()
  elif k=='end':pass
  elif k=='wait':n['frames']=self.frames.value()
  elif k=='call_text':n['npc']=self.call.currentData()
  else:
   n['flag']=self.flag.currentData()
   if k=='if_flag':n.update(is_set=self.condition.currentData(),then=deepcopy(self.node['then']) if self.node else [],otherwise=deepcopy(self.node['otherwise']) if self.node else [])
  for key,_ in branches(n):n[key]=deepcopy(self.node[key]) if self.node else []
  return n
 def accept_checked(self):
  try:compile_actions(self.parent().project,[self.value()],cpu_address(DATA))
  except ValueError as e:self.error.setText(str(e));return
  self.accept()

class CustomEventEditor(QDialog):
 def __init__(self,window,area,index):
  super().__init__(window);self.window=window;self.project=window.project;self.area=area;self.index=index
  obj=self.project.objects(area)[index];self.original_obj=obj;self.original_records=deepcopy(self.project.private_dialogues)
  record=self.project.private_dialogues.get(obj[1]);self.replacing=record is None
  self.actions=deepcopy(record['actions']) if record and 'actions' in record else [{'kind':'say','text':record['text']}] if record else []
  self.saved=deepcopy(self.actions);self.history=[];self.future=[]
  self.setWindowTitle('MysticForge — NPC event editor');self.resize(1050,750);box=QVBoxLayout(self)
  heading=QLabel(f'{self.project.rom.areas[area].name} · Object ${index:02X}');heading.setStyleSheet('font-size:20px;font-weight:bold');box.addWidget(heading)
  note=QLabel('Build this NPC’s interaction from ordered steps. Select a branch (Then, Yes, Received, etc.) to add steps inside it. Moving a branching step moves its entire block. Changes stay here until Apply to project.');note.setWordWrap(True);box.addWidget(note)
  row=QHBoxLayout();box.addLayout(row);self.kind=QComboBox()
  for k,title in KINDS:self.kind.addItem(title,k)
  row.addWidget(self.kind,1)
  self.add_button=QPushButton('Add step');row.addWidget(self.add_button);self.add_button.clicked.connect(self.add)
  self.edit_button=QPushButton('Edit step…');row.addWidget(self.edit_button);self.edit_button.clicked.connect(self.edit)
  self.duplicate=QPushButton('Duplicate');row.addWidget(self.duplicate);self.duplicate.clicked.connect(self.copy_step)
  self.delete=QPushButton('Delete');row.addWidget(self.delete);self.delete.clicked.connect(self.remove)
  self.tree=QTreeWidget();self.tree.setHeaderLabels(['Action / condition']);self.tree.setIndentation(24);box.addWidget(self.tree,1);self.tree.itemDoubleClicked.connect(lambda *_:self.edit());self.tree.itemSelectionChanged.connect(self.selection)
  row=QHBoxLayout();box.addLayout(row)
  self.up=QPushButton('Move up');self.down=QPushButton('Move down');self.undo_button=QPushButton('Undo');self.redo_button=QPushButton('Redo')
  for button in (self.up,self.down,self.undo_button,self.redo_button):row.addWidget(button)
  self.up.clicked.connect(lambda:self.move(-1));self.down.clicked.connect(lambda:self.move(1));self.undo_button.clicked.connect(self.undo);self.redo_button.clicked.connect(self.redo)
  self.status=QLabel();self.status.setWordWrap(True);box.addWidget(self.status)
  limit=QLabel('Choices and rewards have editable outcome branches. Reward messages and one-time flags are explicit steps. Gold grants and arbitrary quest-script calls are not enabled yet.');limit.setWordWrap(True);box.addWidget(limit)
  row=QHBoxLayout();box.addLayout(row);self.apply_button=QPushButton('Apply to project');row.addWidget(self.apply_button);self.apply_button.clicked.connect(self.apply)
  close=QPushButton('Close');row.addWidget(close);close.clicked.connect(self.close);self.rebuild()
 def action_label(self,node):
  if node['kind']=='give_item':
   from .events import inline_name
   from .event_editing import event_rom
   name=inline_name(event_rom(self.project),0x1e,node['item'])
   return f"Give {name} × {node['quantity']}"
  return label(node)
 def resolve(self,path):
  result=self.actions
  for part in path:result=result[part]
  return result
 def path(self):
  item=self.tree.currentItem();return tuple(item.data(0,ROLE)) if item else ()
 def rebuild(self,selected=()):
  self.tree.blockSignals(True);self.tree.clear();root=QTreeWidgetItem(['Actions — run from top to bottom']);root.setData(0,ROLE,());self.tree.addTopLevelItem(root);items={():root}
  def populate(parent,nodes,path):
   for i,n in enumerate(nodes):
    key=path+(i,);item=QTreeWidgetItem([self.action_label(n)]);item.setData(0,ROLE,key);parent.addChild(item);items[key]=item
    if branches(n):
     for branch,title in branches(n):
      bkey=key+(branch,);b=QTreeWidgetItem([title]);b.setData(0,ROLE,bkey);item.addChild(b);items[bkey]=b;populate(b,n[branch],bkey)
  populate(root,self.actions,());self.tree.expandAll();self.tree.setCurrentItem(items.get(selected,root));self.tree.blockSignals(False);self.selection();self.update_status()
 def selection(self):
  path=self.path();node=self.resolve(path);action=isinstance(node,dict)
  for b in (self.edit_button,self.duplicate,self.delete):b.setEnabled(action)
  self.up.setEnabled(action and path[-1]>0);self.down.setEnabled(action and path[-1]+1<len(self.resolve(path[:-1])))
  self.undo_button.setEnabled(bool(self.history));self.redo_button.setEnabled(bool(self.future))
 def change(self,operation,path=()):
  before=deepcopy(self.actions);operation()
  try:compile_actions(self.project,self.actions,cpu_address(DATA))
  except ValueError as e:self.actions=before;self.window.error(e);return
  self.history.append(before);self.future.clear();self.rebuild(path)
 def add(self):
  dialog=ActionDialog(self,self.kind.currentData())
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  path=self.path();container=path if isinstance(self.resolve(path),list) else path[:-1];position=len(self.resolve(container)) if container==path else path[-1]+1
  self.change(lambda:self.resolve(container).insert(position,dialog.value()),container+(position,))
 def edit(self):
  path=self.path();node=self.resolve(path)
  if not isinstance(node,dict):return
  dialog=ActionDialog(self,node['kind'],node)
  if dialog.exec()==QDialog.DialogCode.Accepted:self.change(lambda:self.resolve(path[:-1]).__setitem__(path[-1],dialog.value()),path)
 def copy_step(self):
  path=self.path()
  if path and isinstance(self.resolve(path),dict):self.change(lambda:self.resolve(path[:-1]).insert(path[-1]+1,deepcopy(self.resolve(path))),path[:-1]+(path[-1]+1,))
 def remove(self):
  path=self.path()
  if not path or not isinstance(self.resolve(path),dict):return
  if branches(self.resolve(path)) and QMessageBox.question(self,'Delete branching step?','Delete this step and all steps in its branches?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
  self.change(lambda:self.resolve(path[:-1]).pop(path[-1]),path[:-1])
 def move(self,delta):
  path=self.path()
  if not path or not isinstance(self.resolve(path),dict):return
  nodes=self.resolve(path[:-1]);position=path[-1]+delta
  if 0<=position<len(nodes):self.change(lambda:nodes.insert(position,nodes.pop(path[-1])),path[:-1]+(position,))
 def undo(self):
  if self.history:self.future.append(deepcopy(self.actions));self.actions=self.history.pop();self.rebuild()
 def redo(self):
  if self.future:self.history.append(deepcopy(self.actions));self.actions=self.future.pop();self.rebuild()
 def update_status(self):
  try:
   raw=compile_actions(self.project,self.actions,cpu_address(DATA));entries,writes=plan(self.project);used=sum(len(b) for _,b,_ in writes)
   ident=self.original_obj[1];owners=sum(o[1]==ident and ((o[5]>>3)&3)==0 for a in self.project.rom.areas for o in self.project.objects(a.id))
   old=next((len(b) for at,b,_ in writes if cpu_address(at)==entries.get(ident)),0) if owners==1 else 0
   projected=used-old+len(raw)
   if projected>END-DATA:raise ValueError(f'This event would exceed custom event storage by {projected-(END-DATA)} bytes.')
   self.status.setText(f'Compiled event: {len(raw)} bytes. After applying: {projected} / {END-DATA} bytes of custom event storage. Branch addresses are rebuilt on export.')
   self.apply_button.setEnabled(self.actions!=self.saved or self.replacing)
  except ValueError as e:self.status.setText(str(e));self.apply_button.setEnabled(False)
 def apply(self):
  if self.window.project is not self.project or self.area>=len(self.project.rom.areas) or self.index>=len(self.project.objects(self.area)) or self.project.objects(self.area)[self.index]!=self.original_obj or self.project.private_dialogues!=self.original_records:
   self.window.error('The NPC or custom events changed while this window was open. Close and reopen it before applying.');return False
  if self.replacing and QMessageBox.question(self,'Replace this NPC interaction?','The new steps replace the original interaction, including its quest actions. Other NPCs retain their events. Continue?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return False
  from .expanded_content_editor import commit
  if not commit(self.window,lambda:assign_record(self.project,self.area,self.index,{'actions':deepcopy(self.actions)}),'Edit NPC event'):return False
  self.saved=deepcopy(self.actions);self.replacing=False;self.original_obj=self.project.objects(self.area)[self.index];self.original_records=deepcopy(self.project.private_dialogues);self.update_status();return True
 def allow_close(self):
  if self.actions==self.saved:return True
  answer=QMessageBox.question(self,'Unapplied event changes','Apply your changes before closing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
  return self.apply() if answer==QMessageBox.StandardButton.Save else answer==QMessageBox.StandardButton.Discard
 def closeEvent(self,event):
  if self.allow_close():event.accept()
  else:event.ignore()
 def reject(self):
  if self.allow_close():super().reject()

def show_event_editor(window,area,index):
 p=window.project;objects=p.objects(area)
 if not p.expanded:window.error('Custom NPC events require 1 MiB expanded export.');return
 if not 0<=index<len(objects) or ((objects[index][5]>>3)&3)!=0:window.error('Select an NPC interaction first.');return
 dialog=CustomEventEditor(window,area,index);dialog.exec()
