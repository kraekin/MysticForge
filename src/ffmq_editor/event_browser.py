"""Modeless event search and incoming-reference navigation."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
    QPushButton,QSplitter,QWidget,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QApplication)
from .event_catalog import EventCatalog
from .event_inspector import EventInspector

ROLE=Qt.ItemDataRole.UserRole

class EventBrowser(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.inspector=None;self.stale=False
        self.setWindowTitle('MysticForge — Event browser (read-only)');self.resize(1200,820)
        box=QVBoxLayout(self)
        title=QLabel('Events & references');title.setStyleSheet('font-size:22px;font-weight:bold');box.addWidget(title)
        self.note=QLabel();self.note.setWordWrap(True);box.addWidget(self.note)
        bar=QHBoxLayout();box.addLayout(bar)
        self.search=QLineEdit();self.search.setPlaceholderText('Search dialogue, address, NPC ID, area name or reference…');bar.addWidget(self.search,1)
        self.category=QComboBox();self.category.addItems(['All events','NPC events','World / cutscene events','Text fragments','Linked routines / branches','With map references']);bar.addWidget(self.category)
        refresh=QPushButton('Refresh from project');refresh.clicked.connect(self.refresh);bar.addWidget(refresh)
        flags=QPushButton('Flags & references…');flags.clicked.connect(self.show_flags);bar.addWidget(flags)
        split=QSplitter();box.addWidget(split,1)
        self.list=QTreeWidget();self.list.setHeaderLabels(['Event','Known names / IDs','References']);self.list.setColumnWidth(0,100);self.list.setColumnWidth(1,255);split.addWidget(self.list)
        right=QWidget();layout=QVBoxLayout(right);split.addWidget(right);split.setSizes([500,700])
        self.heading=QLabel();self.heading.setWordWrap(True);layout.addWidget(self.heading)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);layout.addWidget(self.preview,1)
        self.dialogue_button=QPushButton('Preview dialogue…');self.dialogue_button.clicked.connect(self.preview_dialogue);layout.addWidget(self.dialogue_button)
        self.summary_button=QPushButton('Read event summary…');self.summary_button.clicked.connect(self.open_summary);layout.addWidget(self.summary_button)
        self.open_button=QPushButton('Open event flow…');self.open_button.clicked.connect(self.open_event);layout.addWidget(self.open_button)
        layout.addWidget(QLabel('Referenced by — double-click a row to visit its source'))
        self.references=QTreeWidget();self.references.setHeaderLabels(['Type','Source']);self.references.setColumnWidth(0,85);layout.addWidget(self.references,1)
        self.visit_button=QPushButton('Go to selected reference');self.visit_button.clicked.connect(self.visit);layout.addWidget(self.visit_button)
        self.count=QLabel();box.addWidget(self.count)
        close=QPushButton('Close');close.clicked.connect(self.close);box.addWidget(close)
        self.search.textChanged.connect(self.filter);self.category.currentIndexChanged.connect(self.filter)
        self.list.itemSelectionChanged.connect(self.select);self.list.itemDoubleClicked.connect(lambda *_:self.open_event())
        self.references.itemDoubleClicked.connect(lambda *_:self.visit())
        self.references.itemSelectionChanged.connect(lambda:self.visit_button.setEnabled(self.references.currentItem() is not None and self.references.currentItem().data(0,ROLE) is not None))
        window.stack.indexChanged.connect(self.mark_stale)
        self.refresh()

    def mark_stale(self,*_):
        self.stale=True;self.note.setText('Project changed. Refresh to update object and entrance references. This browser is a read-only snapshot.')

    def refresh(self):
        selected=self.list.currentItem();key=selected.data(0,ROLE) if selected else None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:self.catalog=EventCatalog(self.window.rom,self.window.project)
        finally:QApplication.restoreOverrideCursor()
        self.project=self.window.project;self.snapshot_edits=dict(self.project.edits);self.stale=False
        self.note.setText('Read-only snapshot. Search includes dialogue and reference names. References show static calls and both branch outcomes, not a running-game trace. '+ ' '.join(self.catalog.notes))
        self.list.clear();self.items={}
        for key2,record in sorted(self.catalog.records.items(),key=lambda kv:(kv[0][0],kv[0][1] or -1)):
            label=', '.join(sorted(record.aliases)) or 'Linked routine / branch'
            item=QTreeWidgetItem([f'${record.address:06X}',label,str(len(record.references))])
            item.setData(0,ROLE,key2);item.setToolTip(1,label+(f' · bounded to {record.extent} bytes' if record.extent is not None else ''))
            self.list.addTopLevelItem(item);self.items[key2]=item
        self.filter()
        if key in self.items and not self.items[key].isHidden():self.list.setCurrentItem(self.items[key])

    def filter(self,*_):
        query=self.search.text().strip().lower().replace('$','');category=self.category.currentIndex();visible=[]
        for key,item in self.items.items():
            record=self.catalog.records[key];aliases=' '.join(record.aliases)
            category_ok=(category==0 or category==1 and 'NPC ' in aliases or category==2 and 'World /' in aliases or category==3 and 'Text fragment' in aliases or category==4 and not record.aliases or category==5 and any(r.kind in ('Object','Entrance') for r in record.references))
            match=category_ok and all(word in record.search_text.replace('$','') for word in query.split())
            item.setHidden(not match)
            if match:visible.append(item)
        self.count.setText(f'{len(visible)} shown / {len(self.items)} indexed entries · includes unreferenced table entries; no arbitrary ROM scan')
        current=self.list.currentItem()
        if current is None or current.isHidden():self.list.setCurrentItem(visible[0] if visible else None)
        self.select()

    def select(self):
        item=self.list.currentItem();self.references.clear();self.visit_button.setEnabled(False)
        self.open_button.setEnabled(item is not None)
        self.summary_button.setEnabled(item is not None)
        if item is None:self.heading.setText('No matching events');self.preview.clear();self.dialogue_button.setEnabled(False);return
        record=self.catalog.records[tuple(item.data(0,ROLE))]
        names=', '.join(sorted(record.aliases)) or 'Linked routine / branch'
        self.heading.setText(f'{names} · ${record.address:06X}'+(f' · {record.extent}-byte extent' if record.extent is not None else ''))
        issues='\nInspection notes: '+', '.join(sorted(record.issues)) if record.issues else ''
        self.dialogue_button.setEnabled(bool(record.dialogues))
        self.preview.setPlainText(('Dialogue\n\n'+'\n\n'.join(record.dialogues)+'\n\n— Event steps —\n\n' if record.dialogues else '')+record.preview+issues)
        for ref in sorted(record.references,key=lambda r:(r.kind,r.label,r.target)):
            row=QTreeWidgetItem([ref.kind,ref.label]);row.setData(0,ROLE,ref);self.references.addTopLevelItem(row)
        if not record.references:self.references.addTopLevelItem(QTreeWidgetItem(['','No incoming references found in the indexed static sources.']))

    def fresh(self):
        if self.stale or self.project is not self.window.project or self.snapshot_edits!=self.window.project.edits:
            self.refresh();return False
        return True

    def preview_dialogue(self):
        from .dialogue_preview import DialoguePreview
        if not self.fresh():return
        item=self.list.currentItem()
        if item is None:return
        record=self.catalog.records[tuple(item.data(0,ROLE))]
        if record.dialogues:
            self.dialogue_preview=DialoguePreview(self,'\n\n'.join(record.dialogues));self.dialogue_preview.show()

    def open_event(self):
        if not self.fresh():return
        item=self.list.currentItem()
        if item is None:return
        record=self.catalog.records[tuple(item.data(0,ROLE))]
        if self.inspector is not None:self.inspector.close();self.inspector.deleteLater()
        overview='\n'.join([*sorted(record.aliases),f'Event ${record.address:06X}',f'{len(record.references)} static incoming references. Browse references in the event browser.'])
        self.inspector=EventInspector(self.window,f'Event ${record.address:06X}',overview,record.address,extent=record.extent)
        self.inspector.show()

    def open_summary(self):
        self.open_event()
        if self.inspector is not None:self.inspector.tabs.setCurrentWidget(self.inspector.summary)

    def show_flags(self):
        from .flag_browser import FlagBrowser
        if not self.fresh():return
        old=getattr(self,'flag_browser',None)
        if old is not None:old.close();old.deleteLater()
        self.flag_browser=FlagBrowser(self);self.flag_browser.show()

    def visit(self):
        if not self.fresh():return
        item=self.references.currentItem();ref=item.data(0,ROLE) if item else None
        if ref is None:return
        if ref.kind=='Event':
            self.search.clear();self.category.setCurrentIndex(0)
            self.list.setCurrentItem(self.items[ref.target]);self.list.scrollToItem(self.items[ref.target]);return
        area,index=ref.target;w=self.window;w.select_area(area)
        if ref.kind=='Object':
            w.tool.setCurrentText('Objects');w.object_editor.list.setCurrentRow(index)
            obj=w.project.objects(area)[index];x,y=obj[3]&63,obj[2]&63
        else:
            w.show_connections.setChecked(True);w.refresh_map()
            x,y=w.project.fixed('world_node',index)
            for i,entry in enumerate(w.connection_panel.entries):
                if entry.label.startswith(f'World node ${index:02X}'):w.connection_panel.table.selectRow(i);break
        w.canvas.centerOn(x*16+8,y*16+8);w.raise_();w.activateWindow()

def show_browser(window):
    browser=getattr(window,'event_browser',None)
    if browser is None:
        browser=EventBrowser(window);window.event_browser=browser
    elif browser.stale or browser.project is not window.project or browser.snapshot_edits!=window.project.edits:browser.refresh()
    browser.show();browser.raise_();browser.activateWindow()
