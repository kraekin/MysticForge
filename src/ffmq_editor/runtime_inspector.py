"""Evidence-focused view of static runtime dependencies, without executing events."""
from .event_editing import view_rom
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QLineEdit,QTreeWidget,QTreeWidgetItem,QPushButton
from .events import decode

class RuntimeInspector(QWidget):
    def __init__(self,window,entry,extent=None,navigate=None):
        super().__init__();self.navigate=navigate;box=QVBoxLayout(self)
        note=QLabel('Static evidence from this entry and reachable calls. A proven pointer or text value applies only where preceding commands establish it. Branch outcomes and save-state values are not guessed.');note.setWordWrap(True);box.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText('Filter pointers, generated text, actor interactions, or unresolved dependencies…');box.addWidget(self.search)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Evidence','Address','Meaning / dependency']);self.tree.setColumnWidth(0,160);self.tree.setColumnWidth(1,95);box.addWidget(self.tree)
        seen=set()
        for row in decode(view_rom(window),entry,limit=8192,extent=extent):
            text=row.description
            if not any(word in text.lower() for word in ('runtime','proven','interaction reference','generated text')):continue
            if (row.address,text) in seen:continue
            seen.add((row.address,text))
            category='Proven in this path' if 'proven' in text else 'Interaction assignment' if 'interaction reference' in text else 'Runtime dependency'
            item=QTreeWidgetItem([category,f'${row.address:06X}',text]);item.setToolTip(2,text+'\nBytes: '+row.raw.hex(' '));self.tree.addTopLevelItem(item)
            for label,target in row.edges:
                if label in ('call','jump'):
                    child=QTreeWidgetItem(['Candidate' if not row.complete else 'Resolved target',f'${target:06X}','Open this event in Event flow']);child.setData(0,Qt.ItemDataRole.UserRole,target);item.addChild(child)
            if item.childCount():item.setExpanded(True)
        if not seen:self.tree.addTopLevelItem(QTreeWidgetItem(['','', 'No runtime-dependent commands found within this inspection.']))
        self.open_button=QPushButton('Inspect selected target');self.open_button.setEnabled(False);self.open_button.clicked.connect(self.open_target);box.addWidget(self.open_button)
        self.tree.itemSelectionChanged.connect(lambda:self.open_button.setEnabled(self.tree.currentItem() is not None and self.tree.currentItem().data(0,Qt.ItemDataRole.UserRole) is not None))
        self.tree.itemDoubleClicked.connect(lambda *_:self.open_target())
        self.search.textChanged.connect(self.filter)

    def open_target(self):
        item=self.tree.currentItem();target=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if target is not None and self.navigate is not None:self.navigate(target)

    def filter(self,text):
        for i in range(self.tree.topLevelItemCount()):
            item=self.tree.topLevelItem(i);item.setHidden(text.lower() not in ' '.join(item.text(j) for j in range(3)).lower())
