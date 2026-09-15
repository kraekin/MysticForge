"""Small, opt-in patches guarded against the supported USA v1.0 bytes."""
from .rom import FormatError
LIFE_OFFSET=0x1123D # CPU $02:923D, unheadered LoROM

def life_patch(rom):
    # Player Life is action $A0: type $CC -> handler index $0C -> $9209.
    # $02:8B88 masks type to 6 bits; $02:85ED dispatches via $A1D7.
    guards={
        0x140D8:bytes.fromhex('08 80 00 cc d5 15 25'),
        0x10B88:bytes.fromhex('a5 de 29 3f 3f 85 de'),
        0x105E9:bytes.fromhex('a5 de 0a aa fc d7 a1'),
        0x121EF:bytes.fromhex('09 92'),
        0x11234:bytes.fromhex('0b 20 2f 8f a5 2e 2b 29 04 d0 e5 20 d9 97'),
        0x11224:bytes.fromhex('4c 7f 97'),
    }
    if any(rom.data[offset:offset+len(expected)]!=expected for offset,expected in guards.items()):
        raise FormatError('Life fix refused: the USA v1.0 dispatch/instruction sequence does not match.')
    return LIFE_OFFSET,b'\xf0'

def show_fixes(w):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QCheckBox
    dialog=QDialog(w);dialog.setWindowTitle('Optional ROM fixes');dialog.resize(580,220)
    box=QVBoxLayout(dialog)
    label=QLabel('Optional gameplay changes, saved with this project and applied only to exported ROM copies. Changes support Undo/Redo.');label.setWordWrap(True);box.addWidget(label)
    check=QCheckBox('Fix Life spell undead-target check (USA v1.0)');box.addWidget(check)
    note=QLabel('Corrects the inverted undead check in the battle Life handler. Leaves the rest of the spell routine unchanged. Verified against local ROM instructions; battle testing in Mesen is still recommended.');note.setWordWrap(True);box.addWidget(note)
    key=('bugfix',0,0)
    def sync(*_):
        check.blockSignals(True);check.setChecked(bool(w.project.get(key)));check.blockSignals(False)
    sync()
    def toggle(enabled):
        if enabled:
            try:life_patch(w.rom)
            except ValueError as error:w.error(error);sync();return
        old=w.project.get(key);w.commit_changes({key:(old,int(enabled))},'Enable Life spell fix' if enabled else 'Disable Life spell fix')
    check.toggled.connect(toggle);w.stack.indexChanged.connect(sync)
    dialog.finished.connect(lambda *_:w.stack.indexChanged.disconnect(sync))
    w.rom_fixes_dialog=dialog;dialog.show()
