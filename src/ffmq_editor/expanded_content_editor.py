"""Creation controls for bounded expanded resources."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QSpinBox,QComboBox,QPushButton,QMessageBox
from .expansion_editor import snapshot,restore,StructureCommand,show_expansion
from .expanded_content import copy_metatiles,add_entrance

def commit(w,operation,label):
    if not w.confirm_database_edits():return False
    w.end_stroke();before=snapshot(w.project)
    try:
        operation();w.project.validate_expansion();after=snapshot(w.project)
    except (ValueError,IndexError) as error:restore(w.project,before);w.error(error);return False
    restore(w.project,before);w.stack.push(StructureCommand(w,before,after,label));return True

def private_metatiles(w,area_id):
    if not w.project.expanded:show_expansion(w);return
    if QMessageBox.question(w,'Make metatiles independent?',f'Copy all 128 metatile definitions and their gameplay properties for {w.rom.areas[area_id].name}, area ${area_id:02X}?\n\nOther configurations retain their sets. Source pixels, palettes and story remap rules remain shared. New copies use one of 16 private-set slots.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
    commit(w,lambda:copy_metatiles(w.project,area_id),'Make metatile set independent')

def new_entrance(w):
    if not w.project.expanded:show_expansion(w);return
    dialog=QDialog(w);dialog.setWindowTitle('Add a normal door entrance');dialog.resize(610,420);box=QVBoxLayout(dialog)
    note=QLabel('Choose a normal door tile in Tiles first. This creates a coordinate and its own destination, and paints that tile at the source. Base terrain may still be shared. The new link applies only to this configuration. Check the return path separately.');note.setWordWrap(True);box.addWidget(note)
    source_area=w.area_id;brush=w.brush|(128 if w.layer_bit.isChecked() else 0)
    box.addWidget(QLabel(f'Source: {w.rom.areas[source_area].name} · area ${source_area:02X} · tile ${brush:02X}'))
    form=QFormLayout();box.addLayout(form);fields={}
    attrs=w.rom.attributes[w.rom.areas[source_area].attributes_id]
    for name,maximum in [('Source X',attrs.width-1),('Source Y',attrs.height-1)]:
        spin=QSpinBox();spin.setRange(0,maximum);fields[name]=spin;form.addRow(name,spin)
    target=QComboBox()
    from .workspace_ui import version_name
    for area in w.rom.areas:target.addItem(f'{area.name} / {version_name(w,area.id)}',area.id)
    form.addRow('Destination configuration',target)
    for name,maximum in [('Arrival X',63),('Arrival Y',63),('Facing',3)]:
        spin=QSpinBox();spin.setRange(0,maximum);fields[name]=spin;form.addRow(name,spin)
    def bounds():
        a=w.rom.attributes[w.rom.areas[target.currentData()].attributes_id]
        fields['Arrival X'].setMaximum(a.width-1);fields['Arrival Y'].setMaximum(a.height-1)
    target.currentIndexChanged.connect(bounds);bounds()
    add=QPushButton('Create entrance');box.addWidget(add)
    def create():
        if w.area_id!=source_area:w.error('The selected map changed. Reopen Add entrance on the intended map.');return
        v={k:s.value() for k,s in fields.items()};raw=bytes((target.currentData(),v['Arrival Y'],v['Arrival X']|(v['Facing']<<6)))
        if commit(w,lambda:add_entrance(w.project,source_area,v['Source X'],v['Source Y'],raw,brush),'Add entrance and door tile'):
            dialog.accept();w.tool.setCurrentText('Entrances')
    add.clicked.connect(create);w.new_entrance_dialog=dialog;dialog.setModal(True);dialog.show()
