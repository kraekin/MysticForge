"""Guarded dialogue and existing event-parameter editor."""
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QSplitter,QWidget,QListWidget,QPlainTextEdit,QComboBox,QSpinBox,QMessageBox,QApplication)
from .event_editing import (segments_for,tokens,encode_text,change,replacement,event_rom,
                           NAME_OPS,SPECIAL)
from .events import inline_name
from .event_flags import flag_label

class EventEditor(QDialog):
    def __init__(self,window,entry,extent=None):
        super().__init__(window);self.window=window;self.project=window.project;self.entry=entry;self.extent=extent;self.current=None;self.loading=False
        self.setWindowTitle(f'MysticForge — Edit event ${entry:06X}');self.resize(1080,760)
        box=QVBoxLayout(self)
        heading=QLabel('Dialogue & event parameters');heading.setStyleSheet('font-size:22px;font-weight:bold');box.addWidget(heading)
        note=QLabel('Changes apply to this shared event everywhere it is used. Text stays inside its original byte span; calls, branch destinations, page/window commands and shared dictionary definitions are preserved. Apply changes to the project, then export a ROM copy or patch.');note.setWordWrap(True);box.addWidget(note)
        split=QSplitter();box.addWidget(split,1)
        left=QWidget();layout=QVBoxLayout(left);split.addWidget(left)
        layout.addWidget(QLabel('Editable parts of this event'))
        self.list=QListWidget();layout.addWidget(self.list,1)
        self.parts=segments_for(self.project,entry,extent)
        for s in self.parts:
            text=self.part_title(s)
            self.list.addItem(text.replace('\n',' / ')[:110])
            self.list.item(self.list.count()-1).setToolTip(f'${s.address:06X} · {len(s.raw)} bytes\n'+text)
        layout.addWidget(QLabel('Called events are edited separately: expand or focus their steps in Event flow.'))
        refs=QPushButton('Show who uses this event…');refs.clicked.connect(self.references);layout.addWidget(refs)
        right=QWidget();form=QVBoxLayout(right);split.addWidget(right);split.setSizes([350,730])
        self.heading=QLabel();self.heading.setWordWrap(True);form.addWidget(self.heading)
        self.text=QPlainTextEdit();self.text.setPlaceholderText('Type dialogue here. Use Enter for a line break.');self.text.setStyleSheet('font-size:16px');form.addWidget(self.text,1)
        row=QHBoxLayout();form.addLayout(row)
        self.token=QComboBox();row.addWidget(self.token,1)
        for token in SPECIAL:self.token.addItem(token,token)
        for text in ('“','”','…'):self.token.addItem('Punctuation: '+text,text)
        for name,(op,count) in NAME_OPS.items():
            for i in range(count):self.token.addItem(f'{name}: {inline_name(self.project.base_rom,op,i) or i} (${i:02X})',f'[{name}:{i:02X}]')
        self.insert=QPushButton('Insert name / token');self.insert.clicked.connect(lambda:self.text.insertPlainText(self.token.currentData()));row.addWidget(self.insert)
        self.preview_button=QPushButton('Preview dialogue…');self.preview_button.clicked.connect(self.preview);row.addWidget(self.preview_button)
        self.spin=QSpinBox();form.addWidget(self.spin)
        self.flag=QComboBox()
        for i in range(256):self.flag.addItem(flag_label(i),i)
        form.addWidget(self.flag)
        self.budget=QLabel();self.budget.setWordWrap(True);form.addWidget(self.budget)
        self.status=QLabel();self.status.setWordWrap(True);form.addWidget(self.status)
        buttons=QHBoxLayout();form.addLayout(buttons)
        self.apply_button=QPushButton('Apply to project');self.apply_button.clicked.connect(self.apply);buttons.addWidget(self.apply_button)
        self.revert=QPushButton('Discard typing');self.revert.clicked.connect(self.load_current);buttons.addWidget(self.revert)
        self.original=QPushButton('Restore original part');self.original.clicked.connect(self.restore_original);buttons.addWidget(self.original)
        close=QPushButton('Close');close.clicked.connect(self.close);box.addWidget(close)
        self.list.currentRowChanged.connect(self.select)
        self.text.textChanged.connect(self.update_budget);self.spin.valueChanged.connect(self.update_budget);self.flag.currentIndexChanged.connect(self.update_budget)
        if self.parts:self.list.setCurrentRow(0)
        else:
            self.heading.setText('No safely editable parts in this entry. Open a called event from Event flow to edit its dialogue or supported parameters. Shared dictionary bodies and overlapping entry points remain protected.')
            for w in (self.text,self.token,self.insert,self.preview_button,self.spin,self.flag,self.apply_button,self.revert,self.original):w.setEnabled(False)

    def action_title(self,s):
        if s.kind=='text':return 'Dialogue'
        if s.raw[:2]==b'\x05\xe1':return 'Wait'
        if s.raw[:2]==b'\x05\x0b':return 'If game flag is clear'
        return {0x23:'Set game flag',0x2b:'Clear game flag',0x2e:'If game flag is set'}[s.raw[0]]

    def part_title(self,s):
        value=self.project.event_edits.get(s.address,{}).get('value')
        if value is None:value=tokens(self.project.base_rom,s.raw) if s.kind=='text' else s.raw[s.operand]
        return self.action_title(s)+': '+(value or '(empty)' if s.kind=='text' else f'{value} frames' if s.raw[:2]==b'\x05\xe1' else flag_label(value))

    def value(self):
        if self.current.kind=='text':return self.text.toPlainText()
        return self.spin.value() if self.current.raw[:2]==b'\x05\xe1' else self.flag.currentData()

    def saved_value(self):
        s=self.current;r=self.project.event_edits.get(s.address)
        return r['value'] if r else tokens(self.project.base_rom,s.raw) if s.kind=='text' else s.raw[s.operand]

    def dirty(self):return self.current is not None and self.value()!=self.saved_value()

    def allow_discard(self):
        if not self.dirty():return True
        answer=QMessageBox.question(self,'Unapplied changes','Apply your changes before leaving this part?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        return self.apply() if answer==QMessageBox.StandardButton.Save else answer==QMessageBox.StandardButton.Discard

    def select(self,row):
        if self.loading:return
        if not self.allow_discard():
            self.loading=True;self.list.setCurrentRow(self.parts.index(self.current));self.loading=False;return
        self.current=self.parts[row] if row>=0 else None;self.load_current()

    def load_current(self):
        if self.current is None:return
        self.loading=True;s=self.current;istext=s.kind=='text';wait=s.raw[:2]==b'\x05\xe1'
        for w in (self.text,self.token,self.insert,self.preview_button):w.setVisible(istext)
        self.spin.setVisible(not istext and wait);self.flag.setVisible(not istext and not wait)
        self.heading.setText(f'{self.action_title(s)} · ${s.address:06X}'+ ('\nName tokens stay dynamic. Enter adds a line break; message/page commands remain in Event flow.' if istext else '\nOnly the selected parameter changes. The action and its branch destinations stay the same.'))
        item=self.list.item(self.parts.index(s));title=self.part_title(s);item.setText(title.replace('\n',' / ')[:110]);item.setToolTip(f'${s.address:06X} · {len(s.raw)} bytes\n'+title)
        value=self.saved_value()
        if istext:self.text.setPlainText(value)
        elif wait:self.spin.setRange(s.minimum,s.maximum);self.spin.setValue(value)
        else:self.flag.setCurrentIndex(value)
        self.status.clear();self.loading=False;self.update_budget()

    def update_budget(self,*_):
        if self.loading or self.current is None:return
        try:
            s=self.current;raw=replacement(self.project,s,self.value())
            if s.kind=='text':
                used=len(s.raw) if self.value()==tokens(self.project.base_rom,s.raw) else len(encode_text(self.project.base_rom,self.value()))
                self.budget.setText(f'Text budget: {used} / {len(s.raw)} compressed bytes · {len(s.raw)-used} available. Shorter text is padded with invisible no-op commands.')
            else:self.budget.setText('Fixed-size parameter edit · no event addresses move.')
            self.budget.setStyleSheet('color:#a6d5b5');self.apply_button.setEnabled(self.dirty())
        except ValueError as error:self.budget.setText(str(error));self.budget.setStyleSheet('color:#f4b1a7');self.apply_button.setEnabled(False)
        self.revert.setEnabled(self.dirty());self.original.setEnabled(self.current.address in self.project.event_edits)

    def apply(self):
        if self.current is None:return True
        from .expanded_content_editor import commit
        value=self.value();address=self.current.address
        if not commit(self.window,lambda:change(self.project,address,value),'Edit dialogue' if self.current.kind=='text' else 'Edit event parameter'):return False
        self.load_current();self.status.setText('Applied to project. Undo is available in the main window. Export a ROM copy or patch to test in game.');return True

    def restore_original(self):
        if not self.allow_discard():return
        from .expanded_content_editor import commit
        if commit(self.window,lambda:self.project.event_edits.pop(self.current.address,None),'Restore original event part'):self.load_current()

    def preview(self):
        from .dialogue_preview import DialoguePreview
        text=self.text.toPlainText()
        def resolve(m):
            name,i=m[1],int(m[2],16)
            return inline_name(self.project.base_rom,NAME_OPS[name][0],i) or m[0]
        text=re.sub(r'\[(Character|Item|Location|Enemy):([0-9A-Fa-f]{2})\]',resolve,text)
        text=re.sub(r'\[(?:Glyph|Draw glyph):([0-9A-Fa-f]{2})\]',r'[\1]',text).replace('[Spacing]',' ').replace('[Line break or space]','[line break or space]')
        self.preview_dialog=DialoguePreview(self,text);self.preview_dialog.show()

    def references(self):
        from .event_catalog import EventCatalog
        from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:catalog=EventCatalog(event_rom(self.project),self.project)
        finally:QApplication.restoreOverrideCursor()
        keys={k for k in catalog.records if k[0]==self.entry};seen=set();found=set();pending=list(keys)
        while pending:
            key=pending.pop()
            if key in seen:continue
            seen.add(key)
            for ref in catalog.records[key].references:
                found.add((ref.kind,ref.label))
                if ref.kind=='Event':pending.append(ref.target)
        dialog=QDialog(self);dialog.setWindowTitle('Shared event references');dialog.resize(850,550);box=QVBoxLayout(dialog)
        note=QLabel('Static references to this entry and its callers. Runtime-assigned interactions may add other users. Changes affect every path reaching the edited bytes.');note.setWordWrap(True);box.addWidget(note)
        tree=QTreeWidget();tree.setHeaderLabels(['Type','Reference']);tree.setColumnWidth(0,100);box.addWidget(tree)
        for kind,label in sorted(found):tree.addTopLevelItem(QTreeWidgetItem([kind,label]))
        if not found:tree.addTopLevelItem(QTreeWidgetItem(['','No static incoming references found.']))
        dialog.exec()

    def closeEvent(self,event):
        if self.allow_discard():event.accept()
        else:event.ignore()

    def reject(self):
        if self.allow_discard():super().reject()

def show_editor(window,entry,extent=None,address=None):
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:dialog=EventEditor(window,entry,extent)
    except (ValueError,IndexError) as error:window.error(error);return
    finally:QApplication.restoreOverrideCursor()
    if address is not None:
        for i,s in enumerate(dialog.parts):
            if s.address<=address<s.address+len(s.raw):dialog.list.setCurrentRow(i);break
    dialog.exec()
