"""Inspect shared terrain and conditional replacements without changing preview flags."""
from .event_flags import flag_label
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QPushButton
from .workspace_ui import version_name

def show_terrain_uses(w):
    dialog=QDialog(w);dialog.setWindowTitle('Shared terrain uses');dialog.resize(850,480)
    box=QVBoxLayout(dialog)
    note=QLabel('Base edits affect every configuration listed for this layout. Conditional map changes replace the listed rectangles when their flags apply. Visiting a configuration keeps your current preview flags.');note.setWordWrap(True);box.addWidget(note)
    tree=QTreeWidget();tree.setHeaderLabels(['Map / configuration','Conditional tile replacements']);box.addWidget(tree)
    kind,resource=w.target.currentData()
    users=w.project.shared_areas(resource) if kind=='layout' else [a.id for a in w.rom.areas if any(c.opcode==0x22 and c.value==resource for c in w.rom.area_actions[a.id])]
    for area_id in users:
        area=w.rom.areas[area_id];details=[]
        for action in w.rom.area_actions[area_id]:
            if action.opcode!=0x22:continue
            patch=w.rom.changes[action.value]
            details.append(f'{flag_label(action.flag)}: change ${patch.id:02X}, ({patch.x},{patch.y}) to ({patch.x+patch.width-1},{patch.y+patch.height-1})')
        item=QTreeWidgetItem([f'{area.name} / {version_name(w,area_id)}', '; '.join(details) or 'No conditional map-change rectangles recorded'])
        item.setData(0,256,area_id)
        for col in range(2):item.setToolTip(col,item.text(col))
        tree.addTopLevelItem(item)
    tree.resizeColumnToContents(0)
    def visit():
        item=tree.currentItem()
        if item:w.select_area(item.data(0,256))
    button=QPushButton('View selected configuration');button.clicked.connect(visit);box.addWidget(button)
    tree.itemDoubleClicked.connect(lambda *_:visit())
    if tree.topLevelItemCount():tree.setCurrentItem(tree.topLevelItem(0))
    w.terrain_uses_dialog=dialog;dialog.show()

