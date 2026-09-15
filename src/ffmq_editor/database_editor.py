"""
    Editor for managing the in game database. Edits monsters, attacks and spells, weapons, armor, character templates, and battlefield rewards.
    Some stuff is still read only or not here yet, but the goal is to be able to edit everything in the game database.

"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QComboBox,QPushButton,QScrollArea,QFormLayout,QSpinBox,QGroupBox,QSplitter,QMessageBox)
from .database import CATEGORIES,fields,title,proposed_changes

class GameDatabaseWindow(QMainWindow):
    def __init__(self,main_window):
        super().__init__(main_window);self.main_window=main_window;self.loading=False;self.controls=[];self.original={};self.snapshot_project=None;self.current_index=-1;self.current_category=''
        self.setWindowTitle('MysticForge — Game database');self.resize(1050,760)
        root=QWidget();self.setCentralWidget(root);box=QVBoxLayout(root)
        top=QHBoxLayout();top.addWidget(QLabel('Database'));self.category=QComboBox();self.category.addItems(CATEGORIES);top.addWidget(self.category,1)
        undo=QPushButton('Undo');redo=QPushButton('Redo');top.addWidget(undo);top.addWidget(redo);undo.clicked.connect(main_window.stack.undo);redo.clicked.connect(main_window.stack.redo);box.addLayout(top)
        self.notice=QLabel('');self.notice.setWordWrap(True);box.addWidget(self.notice)
        split=QSplitter();box.addWidget(split,1)
        left=QWidget();left_box=QVBoxLayout(left);self.search=QLineEdit();self.search.setPlaceholderText('Find name or hex ID…');left_box.addWidget(self.search);self.records=QListWidget();left_box.addWidget(self.records);split.addWidget(left)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);split.addWidget(self.scroll);split.setSizes([300,700])
        line=QHBoxLayout();self.feedback=QLabel();self.feedback.setWordWrap(True);line.addWidget(self.feedback,1);self.reload_button=QPushButton('Reload record');self.apply_button=QPushButton('Apply changes');line.addWidget(self.reload_button);line.addWidget(self.apply_button);box.addLayout(line)
        self.category.currentTextChanged.connect(self.change_category);self.records.currentRowChanged.connect(self.change_record);self.search.textChanged.connect(self.filter_records)
        self.apply_button.clicked.connect(self.apply);self.reload_button.clicked.connect(self.reload)
        self.change_category(self.category.currentText())
    @property
    def project(self):return self.main_window.project
    def dirty(self):return bool(self.updates())
    def updates(self):
        return [(field,self.value(widget,field)) for field,widget,initial in self.controls if not field.readonly and self.value(widget,field)!=initial]
    def value(self,widget,field):
        if field.readonly:return None
        if field.text:return widget.text()
        if field.choices:return widget.currentData()
        return widget.value()
    def confirm_navigation(self):
        if not self.dirty():return True
        answer=QMessageBox.question(self,'Unapplied database edits','Apply changes before leaving this record?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Cancel:return False
        if answer==QMessageBox.StandardButton.Save:return self.apply()
        self.load_record(self.current_index)
        return True
    def change_category(self,category):
        if self.loading:return
        if not self.confirm_navigation():
            self.category.blockSignals(True);self.category.setCurrentText(self.current_category);self.category.blockSignals(False);return
        self.current_category=category;self.current_index=-1;self.controls=[]
        self.records.blockSignals(True);self.records.clear()
        for i in range(CATEGORIES[category]):self.records.addItem(f'${i:02X} · {title(self.project,category,i)}')
        self.records.setCurrentRow(0);self.records.blockSignals(False);self.load_record(0);self.filter_records()
    def filter_records(self,*_):
        query=self.search.text().casefold()
        for i in range(self.records.count()):self.records.item(i).setHidden(query not in self.records.item(i).text().casefold())
    def change_record(self,index):
        if self.loading or index<0:return
        if not self.confirm_navigation():
            self.records.blockSignals(True);self.records.setCurrentRow(self.current_index);self.records.blockSignals(False);return
        self.load_record(index)
    def load_record(self,index):
        self.loading=True;self.controls=[];self.current_index=index;self.snapshot_project=self.project
        fs=fields(self.current_category,index);self.original={f.kind:self.project.fixed(f.kind,index) for f in fs}
        root=QWidget();box=QVBoxLayout(root);groups={}
        heading=QLabel(title(self.project,self.current_category,index));heading.setObjectName('heading');box.addWidget(heading)
        for field in fs:
            if field.group not in groups:
                group=QGroupBox(field.group);outer=QVBoxLayout(group);body=QWidget();form=QFormLayout(body);outer.addWidget(body);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);groups[field.group]=form;box.addWidget(group)
                if field.group=='Technical data':
                    group.setCheckable(True);group.setChecked(False);body.setVisible(False);group.toggled.connect(body.setVisible)
            value=field.read(self.original[field.kind])
            if field.readonly:widget=QLabel(f'${value:0{field.size*2}X} · read-only')
            elif field.text:widget=QLineEdit(value)
            elif field.choices:
                widget=QComboBox()
                for v,label in field.choices:
                    if field.kind=='monster_attacks' and 1<=field.offset<=6 and v<169:label=f'${v:02X} · {title(self.project,"Attacks & spells",v)}'
                    widget.addItem(label,v)
                idx=widget.findData(value)
                if idx<0:widget.addItem(f'Unknown ${value:X} — preserved',value);idx=widget.count()-1
                widget.setCurrentIndex(idx);widget.currentIndexChanged.connect(self.mark_dirty)
            else:
                widget=QSpinBox();mask=field.mask if field.mask is not None else (1<<(8*field.size))-1
                widget.setRange(0,mask//(mask&-mask));widget.setValue(value);widget.valueChanged.connect(self.mark_dirty)
            if field.text:widget.textChanged.connect(self.mark_dirty)
            widget.setToolTip(f'{field.kind} · record ${index:02X} · byte ${field.offset:02X}'+(' · preserves unrelated bits' if field.mask else ''))
            groups[field.group].addRow(field.label,widget);self.controls.append((field,widget,None if field.readonly else value))
        box.addStretch();old=self.scroll.takeWidget()
        if old:old.deleteLater()
        self.scroll.setWidget(root)
        if self.current_category=='Battlefield rewards':
            from .content_editor import ITEM_NAMES
            chooser=QComboBox();chooser.addItem('Choose an item reward…',None)
            for i,label in enumerate(ITEM_NAMES):chooser.addItem(f'${i:02X} · {label}',i)
            def choose_item(_):
                item=chooser.currentData()
                if item is None:return
                for f,w,_ in self.controls:
                    if f.label=='Reward type':w.setCurrentIndex(w.findData(1))
                    elif f.label=='Payload (raw units)':w.setValue(item)
            chooser.currentIndexChanged.connect(choose_item);groups['General'].addRow('Assign item reward',chooser)
            raw=int.from_bytes(self.original['battlefield'],'little')
            if raw>>14==1 and (raw&0x3fff)<64:groups['General'].addRow('Current item',QLabel(ITEM_NAMES[raw&0x3fff]))
        message='Edits apply to this project and exported ROM copies. Unknown fields are read-only; unedited bytes are preserved.'
        if self.current_category=='Character templates':message+=' These are initialization templates, not current characters or save data; the engine may recalculate effective stats.'
        if self.current_category=='Battlefield rewards':message+=' Amounts are stored units, not a promised displayed payout. Item payloads use item IDs $00–$3F.'
        if self.current_category=='Monsters' and index>=79:message+=' This extra statistics slot has no separate name. Dark King phase scripts may override its stored attack list.'
        self.notice.setText(message);self.feedback.setText('No unapplied changes');self.apply_button.setEnabled(False);self.loading=False
    def mark_dirty(self,*_):
        if self.loading:return
        n=len(self.updates());self.apply_button.setEnabled(bool(n));self.feedback.setText(f'{n} changed field(s) — not applied yet' if n else 'No unapplied changes')
    def apply(self):
        try:
            if self.snapshot_project is not self.project:raise ValueError('A different project is open. Reload this record before editing.')
            diff=proposed_changes(self.project,self.current_index,self.original,self.updates())
            # Validate before committing, so rejected input cannot enter the undo stack.
            from .database import validate_record
            kinds={key[0] for key in diff}
            for kind in kinds:
                raw=bytearray(self.original[kind])
                for (k,_,i),(_,value) in diff.items():
                    if k==kind:raw[i]=value
                validate_record(self.project,kind,self.current_index,bytes(raw))
            self.loading=True
            self.main_window.commit_changes(diff,f'Edit {self.current_category}: {title(self.project,self.current_category,self.current_index)}')
            self.load_record(self.current_index);self.refresh_names();self.feedback.setText(f'Applied {len(diff)} byte change(s)' if diff else 'No changes to apply');return True
        except ValueError as error:self.feedback.setText(str(error));return False
        finally:self.loading=False
    def refresh_names(self):
        self.records.blockSignals(True)
        for i in range(self.records.count()):self.records.item(i).setText(f'${i:02X} · {title(self.project,self.current_category,i)}')
        self.records.blockSignals(False);self.filter_records()
    def project_changed(self):
        if self.loading:return
        if self.dirty():self.feedback.setText('Project changed. Apply checks for conflicts; Reload discards unapplied fields.');return
        self.load_record(self.current_index);self.refresh_names()
    def reload(self):
        if self.dirty() and not self.confirm_navigation():return
        self.load_record(self.current_index);self.refresh_names()
    def closeEvent(self,event):
        if self.confirm_navigation():event.accept()
        else:event.ignore()

def open_database(w):
    if not hasattr(w,'database_window'):w.database_window=GameDatabaseWindow(w)
    else:w.database_window.project_changed()
    w.database_window.show();w.database_window.raise_();w.database_window.activateWindow()
