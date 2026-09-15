"""Explicit ROM-size choice and scoped terrain-copy operations."""
from copy import deepcopy
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QMessageBox

def snapshot(project):
    return deepcopy((project.expanded,project.layout_copies,project.layout_bindings,project.content,project.world,project.landmarks,project.newmaps,project.sprite_sets,project.event_edits,project.setup_labels,project.edits))

def restore(project,state):
    project.expanded,project.layout_copies,project.layout_bindings,project.content,project.world,project.landmarks,project.newmaps,project.sprite_sets,project.event_edits,project.setup_labels,project.edits=deepcopy(state)
    from .new_maps import sync_catalog
    sync_catalog(project)

class StructureCommand(QUndoCommand):
    def __init__(self,w,before,after,label):
        super().__init__(label);self.w=w;self.before=before;self.after=after
    def apply(self,state):
        p=self.w.project;restore(p,state)
        p.validate_expansion()
        if hasattr(self.w,'event_browser'):self.w.event_browser.stale=True
        self.w.refresh()
    def undo(self):self.apply(self.before)
    def redo(self):self.apply(self.after)

def set_expansion(w,enabled):
    if not w.confirm_database_edits():return False
    w.end_stroke();p=w.project
    if p.expanded==enabled:return True
    from .expanded_content import active
    if not enabled and (p.layout_copies or active(p) or p.world["routes"] or p.world["nodes"] or (p.landmarks is not None and len(p.landmarks)>143)):
        QMessageBox.information(w,'Content needs expansion','This project contains expanded resources. Keep expanded export enabled, or undo their creation first.');return False
    before=snapshot(p);after=(enabled,*before[1:])
    w.stack.push(StructureCommand(w,before,after,'Enable 1 MiB export' if enabled else 'Use original ROM size'))
    return True

def show_expansion(w,startup=False):
    dialog=QDialog(w);dialog.setWindowTitle('Choose ROM size' if startup else 'ROM expansion');dialog.resize(620,310)
    box=QVBoxLayout(dialog);title=QLabel('More room for map editing');title.setObjectName('heading');box.addWidget(title)
    note=QLabel('Expand the working project to 1 MiB for additional terrain storage, independent terrain/metatile copies, extra field objects and normal door entrances, or keep the original 512 KiB size. Your original ROM file stays unchanged.\n\nExpanded ROMs are created with Export ROM copy. Share expanded projects as BPS patches; IPS export requires the original size. This development feature still needs in-game acceptance testing.');note.setWordWrap(True);box.addWidget(note)
    status=QLabel('Current project: '+('1 MiB expanded export' if w.project.expanded else '512 KiB original size'));box.addWidget(status)
    row=QHBoxLayout();box.addLayout(row)
    keep=QPushButton('Keep original size');expand=QPushButton('Expand to 1 MiB');row.addWidget(keep);row.addWidget(expand)
    keep.clicked.connect(lambda:dialog.accept() if set_expansion(w,False) else None)
    expand.clicked.connect(lambda:dialog.accept() if set_expansion(w,True) else None)
    w.expansion_dialog=dialog;dialog.setModal(True);dialog.show()

def copy_terrain(w):
    if not w.confirm_database_edits():return
    w.end_stroke();p=w.project;area=w.rom.areas[w.area_id]
    if not p.expanded:
        show_expansion(w);return
    members=[a.id for a in w.rom.areas if a.offset==area.offset]
    from .workspace_ui import version_name
    labels='\n'.join(f'• {version_name(w,i)}' for i in members)
    note=('Copy current base terrain for:\n'+labels+'\n\nOther configurations retain their terrain. Objects, entrances, palettes, graphics and restoration changes remain shared. Restoration changes may still replace some tiles in this copy.')
    if len(members)>1:note+='\n\nThese configurations share one area record and must move together in this version.'
    if QMessageBox.question(w,'Make terrain independent?',note,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
    before=snapshot(p)
    try:
        p.copy_terrain(w.area_id);after=snapshot(p)
    except ValueError as error:
        restore(p,before);w.error(error);return
    restore(p,before)
    w.stack.push(StructureCommand(w,before,after,'Make terrain independent'))
