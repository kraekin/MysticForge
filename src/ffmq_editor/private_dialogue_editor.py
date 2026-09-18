"""NPC-scoped conversation editor, independent of the shared event editor."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QMessageBox
from .private_dialogue import assign,compile_text,plan,DATA,END

def show_dialogue(window,area,index):
    p=window.project;objects=p.objects(area)
    if not 0<=index<len(objects):window.error('Select an NPC on the map or an Object reference first.');return
    obj=objects[index]
    if (obj[5]>>3)&3:window.error('This option is for NPCs. Chests and encounters use their own editors.');return
    if not p.expanded:window.error('Enable 1 MiB export in ROM expansion before customizing NPC dialogue.');return
    current=p.private_dialogues.get(obj[1])
    if current and 'actions' in current:
        from .custom_event_editor import show_event_editor
        show_event_editor(window,area,index);return
    dialog=QDialog(window);dialog.setWindowTitle('Edit NPC dialogue' if current else 'Customize NPC dialogue');dialog.resize(800,560);box=QVBoxLayout(dialog)
    title=QLabel(f'{p.rom.areas[area].name} · Object ${index:02X}');title.setStyleSheet('font-size:20px;font-weight:bold');box.addWidget(title)
    note=QLabel('Give this NPC its own conversation without changing other NPCs. This replaces the selected interaction; it does not copy battles, rewards, conditions, movement or quest actions. Scripted reassignment can still change an NPC during play.\n\nUse Enter for a line break. Text uses expanded storage; insert names using the token picker. Hero, companion and number values are filled in during play.');note.setWordWrap(True);box.addWidget(note)
    initial=current['text'] if current else ''
    if not current:
        from .event_editing import event_rom,tokens
        from .events import npc_entry,decode
        rom=event_rom(p);entry=npc_entry(rom,obj[1])
        if entry is not None:
            rows=decode(rom,entry,follow_calls=False)
            if rows and rows[-1].raw==b'\x00':
                candidate=tokens(rom,b''.join(r.raw for r in rows[:-1]))
                if candidate:
                    try:compile_text(candidate);initial=candidate
                    except ValueError:pass
    text=QPlainTextEdit();text.setPlaceholderText('Write the NPC’s dialogue…');text.setPlainText(initial);box.addWidget(text,1)
    from .dialogue_tokens import add_token_picker,preview_text,wrap_text
    token_row=QHBoxLayout();box.addLayout(token_row);add_token_picker(token_row,text,p.base_rom)
    budget=QLabel();budget.setWordWrap(True);box.addWidget(budget)
    row=QHBoxLayout();box.addLayout(row);preview=QPushButton('Preview');save=QPushButton('Apply NPC dialogue');cancel=QPushButton('Cancel');row.addWidget(preview);wrap=QPushButton('Wrap lines');row.addWidget(wrap);row.addStretch();row.addWidget(save);row.addWidget(cancel)
    def update():
        try:
            raw=compile_text(text.toPlainText());used=sum(len(raw) for _,raw,_ in plan(p)[1])
            budget.setText(f'{len(raw)} bytes including return · shared dialogue storage: {used} / {END-DATA} bytes currently used.');save.setEnabled(True)
        except ValueError as e:budget.setText(str(e));save.setEnabled(False)
    def wrap_lines():
        text.setPlainText(wrap_text(p.base_rom,text.toPlainText()))
    wrap.clicked.connect(wrap_lines)
    wrap.setToolTip('Wrap to 28 cells without splitting tokens. Dynamic values reserve 8 cells; verify in game.')
    def show_preview():
        from .dialogue_preview import DialoguePreview
        dialog.preview=DialoguePreview(dialog,preview_text(p.base_rom,text.toPlainText()));dialog.preview.show()
    def apply():
        if window.project is not p:window.error('The project changed. Reopen this editor.');return
        if not current and QMessageBox.question(dialog,'Replace this NPC interaction?', 'This NPC will only say the new dialogue. Any original quest actions, rewards or battle triggers on this interaction will no longer run. Other NPCs keep their events. Continue?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        from .expanded_content_editor import commit
        if commit(window,lambda:assign(p,area,index,text.toPlainText()),'Edit NPC dialogue' if current else 'Customize NPC dialogue'):dialog.accept()
    text.textChanged.connect(update);preview.clicked.connect(show_preview);save.clicked.connect(apply);cancel.clicked.connect(dialog.reject);update();dialog.exec()
