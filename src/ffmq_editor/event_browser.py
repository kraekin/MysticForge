"""Modeless event search and incoming-reference navigation."""
from .event_editing import event_rom
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
    QPushButton,QSplitter,QWidget,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QApplication,QTabWidget)
from .event_catalog import EventCatalog
from .event_inspector import EventInspector

ROLE=Qt.ItemDataRole.UserRole

class EventBrowser(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.inspector=None;self.stale=False
        self.setWindowTitle('MysticForge — Event browser');self.resize(1200,820)
        box=QVBoxLayout(self)
        title=QLabel('Events & references');title.setStyleSheet('font-size:22px;font-weight:bold');box.addWidget(title)
        self.note=QLabel();self.note.setWordWrap(True);box.addWidget(self.note)
        bar=QHBoxLayout();box.addLayout(bar)
        self.search=QLineEdit();self.search.setPlaceholderText('Search dialogue, address, NPC ID, area name or reference…');bar.addWidget(self.search,1)
        self.category=QComboBox();self.category.addItems(['All events','NPC events','World / cutscene events','Text fragments','Linked routines / branches','With map references','Current map']);bar.addWidget(self.category)
        self.search.setClearButtonEnabled(True)
        refresh=QPushButton('Refresh from project');refresh.clicked.connect(self.refresh);bar.addWidget(refresh)
        flags=QPushButton('Flags & references…');flags.clicked.connect(self.show_flags);bar.addWidget(flags)
        split=QSplitter();box.addWidget(split,1)
        self.list=QTreeWidget();self.list.setHeaderLabels(['Event / NPC','Address','Uses']);self.list.setColumnWidth(0,285);self.list.setColumnWidth(1,100);split.addWidget(self.list)
        right=QWidget();layout=QVBoxLayout(right);split.addWidget(right);split.setSizes([500,700])
        self.heading=QLabel();self.heading.setWordWrap(True);layout.addWidget(self.heading)
        self.scope=QLabel();self.scope.setWordWrap(True);layout.addWidget(self.scope)
        self.details=QTabWidget();layout.addWidget(self.details,1)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setStyleSheet('font-size:15px;');self.details.addTab(self.preview,'Dialogue and actions')
        actions=QHBoxLayout();layout.addLayout(actions)
        self.dialogue_button=QPushButton('Preview…');self.dialogue_button.clicked.connect(self.preview_dialogue);actions.addWidget(self.dialogue_button)
        self.summary_button=QPushButton('Summary…');self.summary_button.clicked.connect(self.open_summary);actions.addWidget(self.summary_button)
        self.open_button=QPushButton('Event flow…');self.open_button.clicked.connect(self.open_event);actions.addWidget(self.open_button)
        self.edit_button=QPushButton('Edit shared dialogue / parameters…');self.edit_button.clicked.connect(self.edit_event);actions.addWidget(self.edit_button)
        self.scene_button=QPushButton('Open in scene editor…');layout.addWidget(self.scene_button);self.scene_button.clicked.connect(self.open_scene)
        self.reference_note=QLabel('Select an Object reference to visit its NPC or customize its dialogue.');self.reference_note.setWordWrap(True);layout.addWidget(self.reference_note)
        self.references=QTreeWidget();self.references.setHeaderLabels(['Type','Source']);self.references.setColumnWidth(0,85);self.details.addTab(self.references,'Used by')
        self.visit_button=QPushButton('Go to selected reference');self.visit_button.clicked.connect(self.visit);navigation=QHBoxLayout();layout.addLayout(navigation);navigation.addWidget(self.visit_button)
        self.private_button=QPushButton('Customize NPC dialogue…');navigation.addWidget(self.private_button);self.private_button.clicked.connect(self.independent_dialogue)
        self.event_button=QPushButton('Customize NPC event…');navigation.addWidget(self.event_button);self.event_button.clicked.connect(self.custom_event)
        self.count=QLabel();box.addWidget(self.count)
        close=QPushButton('Close');close.clicked.connect(self.close);box.addWidget(close)
        self.search.textChanged.connect(self.filter);self.category.currentIndexChanged.connect(self.filter)
        self.list.itemSelectionChanged.connect(self.select);self.list.itemDoubleClicked.connect(lambda *_:self.open_event())
        self.references.itemDoubleClicked.connect(lambda *_:self.visit())
        self.references.itemSelectionChanged.connect(self.reference_selected)
        window.stack.indexChanged.connect(self.mark_stale)
        self.refresh()

    def mark_stale(self,*_):
        self.stale=True;self.note.setText('Project changed. Refresh to update object and entrance references. This browser is a project snapshot.')

    def refresh(self):
        selected=self.list.currentItem();key=tuple(selected.data(0,ROLE)) if selected else None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:self.catalog=EventCatalog(event_rom(self.window.project),self.window.project)
        finally:QApplication.restoreOverrideCursor()
        self.project=self.window.project;self.snapshot_edits=dict(self.project.edits);self.snapshot_events=dict(self.project.event_edits);self.snapshot_private=dict(self.project.private_dialogues);self.stale=False
        self.note.setText('Search for words an NPC says, a map name, or an event ID. Select an event to read it; Used by shows where it is referenced. '+ ' '.join(self.catalog.notes))
        self.list.clear();self.items={}
        for key2,record in sorted(self.catalog.records.items(),key=lambda kv:(not any(r.kind=='Object' for r in kv[1].references),not bool(kv[1].aliases),kv[0][0],kv[0][1] or -1)):
            label=', '.join(sorted(record.aliases)) or 'Linked routine / branch'
            objects=[r for r in record.references if r.kind=='Object']
            display=objects[0].label if len(objects)==1 else label
            if record.address in getattr(event_rom(self.window.project),'private_npc_entries',{}).values():display='Custom NPC · '+display
            item=QTreeWidgetItem([display,f'${record.address:06X}',str(len(record.references))])
            item.setData(0,ROLE,key2);item.setToolTip(0,label+(f' · bounded to {record.extent} bytes' if record.extent is not None else ''))
            self.list.addTopLevelItem(item);self.items[key2]=item
        self.filter()
        if key in self.items and not self.items[key].isHidden():self.list.setCurrentItem(self.items[key])

    def filter(self,*_):
        query=self.search.text().strip().lower().replace('$','');category=self.category.currentIndex();visible=[]
        for key,item in self.items.items():
            record=self.catalog.records[key];aliases=' '.join(record.aliases)
            category_ok=(category==0 or category==1 and 'NPC ' in aliases or category==2 and ('World /' in aliases or 'opening cutscene' in aliases) or category==3 and 'Text fragment' in aliases or category==4 and not record.aliases or category==5 and any(r.kind in ('Object','Entrance') for r in record.references) or category==6 and any(r.kind in ('Object','Entrance') and r.target[0]==self.window.area_id for r in record.references))
            match=category_ok and all(word in record.search_text.replace('$','') for word in query.split())
            item.setHidden(not match)
            if match:visible.append(item)
        self.count.setText(f'{len(visible)} shown / {len(self.items)} indexed entries · includes unreferenced table entries; no arbitrary ROM scan')
        current=self.list.currentItem()
        if current is None or current.isHidden():self.list.setCurrentItem(visible[0] if visible else None)
        self.select()

    def select(self):
        item=self.list.currentItem();self.references.clear();self.visit_button.setEnabled(False)
        self.private_button.setEnabled(False)
        self.event_button.setEnabled(False)
        self.scope.clear()
        self.open_button.setEnabled(item is not None);self.scene_button.setEnabled(item is not None)
        self.edit_button.setEnabled(item is not None)
        self.summary_button.setEnabled(item is not None)
        if item is None:self.heading.setText('No matching events');self.preview.clear();self.dialogue_button.setEnabled(False);return
        record=self.catalog.records[tuple(item.data(0,ROLE))]
        names=', '.join(sorted(record.aliases)) or 'Linked routine / branch'
        owners=[r.label for r in record.references if r.kind=='Object']
        if len(owners)==1:names=owners[0]+' · '+names
        self.heading.setStyleSheet('font-size:17px;font-weight:bold')
        private=record.address in getattr(event_rom(self.window.project),'private_npc_entries',{}).values()
        objects=sum(r.kind=='Object' for r in record.references)
        ident=next((i for i,a in getattr(event_rom(self.window.project),'private_npc_entries',{}).items() if a==record.address),None)
        structured=ident is not None and 'actions' in self.window.project.private_dialogues[ident]
        self.scope.setText(('Custom NPC event.' if structured else 'Custom NPC dialogue.' if private else 'Shared event: edits affect every use of these bytes.')+f' {objects} direct object reference(s). Calls and runtime assignments may add other users.')
        self.edit_button.setText('Edit NPC event…' if structured else 'Edit NPC dialogue…' if private else 'Edit shared dialogue / parameters…')
        if not private:
            from .event_editing import segments_for
            editable=bool(segments_for(self.window.project,record.address,record.extent))
            self.edit_button.setEnabled(editable)
            self.edit_button.setToolTip('Edit the supported dialogue and parameter spans used by every caller.' if editable else 'No editable spans here. Open Event flow and expand its called events to find dialogue.')
        else:self.edit_button.setToolTip('Edit the selected NPC conversation in expanded storage.')
        self.details.setTabText(1,f'Used by ({len(record.references)})')
        self.heading.setText(f'{names} · ${record.address:06X}'+(f' · {record.extent}-byte extent' if record.extent is not None else ''))
        issues='\nInspection notes: '+', '.join(sorted(record.issues)) if record.issues else ''
        self.dialogue_button.setEnabled(bool(record.dialogues))
        self.preview.setPlainText(('Dialogue\n\n'+'\n\n'.join(record.dialogues)+'\n\n— Event steps —\n\n' if record.dialogues else '')+record.action_preview+issues)
        for ref in sorted(record.references,key=lambda r:(r.kind,r.label,r.target)):
            row=QTreeWidgetItem([ref.kind,ref.label]);row.setData(0,ROLE,ref);self.references.addTopLevelItem(row)
        if not record.references:self.references.addTopLevelItem(QTreeWidgetItem(['','No incoming references found in the indexed static sources.']))

    def fresh(self):
        if self.stale or self.project is not self.window.project or self.snapshot_edits!=self.window.project.edits or self.snapshot_events!=self.window.project.event_edits or self.snapshot_private!=self.window.project.private_dialogues:
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

    def open_scene(self):
        item=self.list.currentItem()
        if item is None:return
        record=self.catalog.records[tuple(item.data(0,ROLE))]
        from .scene_editor import open_workspace
        areas={r.target[0] for r in record.references if r.kind in ('Object','Entrance')}
        open_workspace(self.window,record.address,next(iter(areas)) if len(areas)==1 else None,record.extent)

    def edit_event(self):
        if not self.fresh():return
        item=self.list.currentItem()
        if item is None:return
        record=self.catalog.records[tuple(item.data(0,ROLE))]
        if record.address in getattr(event_rom(self.window.project),'private_npc_entries',{}).values():
            refs=[r for r in record.references if r.kind=='Object']
            if len(refs)==1:
                from .private_dialogue_editor import show_dialogue
                show_dialogue(self.window,*refs[0].target);self.refresh()
            else:
                self.details.setCurrentWidget(self.references)
                self.scope.setText('Select an Object reference in Used by, then customize its dialogue. Other NPCs keep their conversations.')
            return
        from .event_editor import show_editor
        show_editor(self.window,record.address,record.extent)
        self.refresh()

    def open_summary(self):
        self.open_event()
        if self.inspector is not None:self.inspector.tabs.setCurrentWidget(self.inspector.summary)

    def show_flags(self):
        from .flag_browser import FlagBrowser
        if not self.fresh():return
        old=getattr(self,'flag_browser',None)
        if old is not None:old.close();old.deleteLater()
        self.flag_browser=FlagBrowser(self);self.flag_browser.show()

    def reference_selected(self):
        item=self.references.currentItem();ref=item.data(0,ROLE) if item else None
        self.visit_button.setEnabled(ref is not None)
        npc=False;custom=False
        if ref is not None and ref.kind=='Object':
            area,index=ref.target;objects=self.window.project.objects(area)
            if 0<=index<len(objects):
                obj=objects[index];npc=((obj[5]>>3)&3)==0
                custom=npc and obj[1] in self.window.project.private_dialogues
        structured=custom and 'actions' in self.window.project.private_dialogues[obj[1]]
        self.event_button.setEnabled(npc)
        self.event_button.setText('Edit NPC event…' if structured else 'Customize NPC event…')
        self.private_button.setEnabled(npc and not structured)
        self.private_button.setText('Edit NPC dialogue…' if custom else 'Customize NPC dialogue…')
        self.private_button.setToolTip('Give this NPC its own conversation without changing other NPCs.')

    def custom_event(self):
        if not self.fresh():return
        item=self.references.currentItem();ref=item.data(0,ROLE) if item else None
        if ref is None or ref.kind!='Object':return
        from .custom_event_editor import show_event_editor
        show_event_editor(self.window,*ref.target);self.refresh()

    def independent_dialogue(self):
        if not self.fresh():return
        item=self.references.currentItem();ref=item.data(0,ROLE) if item else None
        if ref is None or ref.kind!='Object':return
        from .private_dialogue_editor import show_dialogue
        show_dialogue(self.window,*ref.target);self.refresh()

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
    elif browser.stale or browser.project is not window.project or browser.snapshot_edits!=window.project.edits or browser.snapshot_events!=window.project.event_edits or browser.snapshot_private!=window.project.private_dialogues:browser.refresh()
    browser.show();browser.raise_();browser.activateWindow()
