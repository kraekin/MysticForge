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

def new_entrance(w,position=None):
    if not w.project.expanded:show_expansion(w);return
    from .entrance_destination import DestinationDialog
    source_area=w.area_id;project=w.project;brush=w.brush|(128 if w.layer_bit.isChecked() else 0)
    attrs=w.rom.attributes[w.rom.areas[source_area].attributes_id]
    x=QSpinBox();y=QSpinBox();x.setRange(0,attrs.width-1);y.setRange(0,attrs.height-1)
    if position:x.setValue(position[0]);y.setValue(position[1])
    def create(raw):
        if w.project is not project or w.area_id!=source_area:w.error('The source map changed. Reopen Add entrance.');return False
        result=commit(w,lambda:add_entrance(project,source_area,x.value(),y.value(),raw,brush),'Add entrance and destination')
        if result:
            w.tool.setCurrentText('Entrances')
            for row,e in enumerate(w.connection_panel.entries):
                if (e.x,e.y)==(x.value(),y.value()):w.connection_panel.table.selectRow(row);break
        return result
    dialog=DestinationDialog(w,bytes((source_area,0,0)),create,'Add entrance — choose destination',
        'Choose the destination map, then click the arrival square. This creates a new destination for this entrance and paints the selected normal door tile. The return path is separate.')
    form=QFormLayout();form.addRow(f'Source X · {w.rom.areas[source_area].name}',x);form.addRow('Source Y',y);dialog.layout().insertLayout(1,form)
    dialog.apply_button.setText('Create entrance');w.new_entrance_dialog=dialog;dialog.setModal(True);dialog.show()
