"""Standalone, read-only snapshots of selected objects and connections."""
from .event_flags import flag_label
from .event_editing import view_rom
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QTabWidget,QPlainTextEdit,QTreeWidget,QTreeWidgetItem,QPushButton,QHBoxLayout,QTextBrowser
from html import escape
from .events import decode,world_entry,npc_entry
from .rom import pc,read,u16
from .content_editor import ITEM_NAMES,enemy_name
from .object_editor import FIELDS
from .event_flow_view import EventFlowView
from .object_behavior import object_behavior

class EventInspector(QDialog):
    def __init__(self,window,title,overview,entry=None,behavior=None,extent=None):
        super().__init__(window);self.window=window;self.setWindowTitle(title+" — Inspector (read-only)");self.resize(1050,740)
        box=QVBoxLayout(self);label=QLabel(title);label.setStyleSheet("font-size:20px;font-weight:bold");box.addWidget(label)
        note=QLabel("Read-only snapshot of the current project. Both branch paths are shown; gameplay, dialogue and timing are not executed. Reopen to refresh after edits.");note.setWordWrap(True);box.addWidget(note)
        self.tabs=QTabWidget();box.addWidget(self.tabs)
        self.overview=QPlainTextEdit();self.overview.setReadOnly(True);self.overview.setPlainText(overview);self.tabs.addTab(self.overview,"Details & references")
        self.flow=QTreeWidget();self.flow.setHeaderLabels(["CPU address","Action / control flow","Bytes"]);self.flow.setColumnWidth(0,115);self.flow.setColumnWidth(1,620);self.tabs.addTab(self.flow,"Event flow")
        self.raw=QPlainTextEdit();self.raw.setReadOnly(True);self.tabs.addTab(self.raw,"Raw current-event bytes")
        if behavior is not None:
            self.behavior=QTextBrowser();self.behavior.setOpenExternalLinks(False)
            profile,uses=behavior
            if profile is None:
                self.behavior.setPlainText('This object has no verified profile in the 87-record v1.0 table. No movement program is inferred from the following ROM data.')
            else:
                fields=''.join(f'<tr><td style="padding:8px;color:#9acddd">{escape(k)}</td><td style="padding:8px">{escape(v)}</td></tr>' for k,v in profile.fields())
                self.behavior.setHtml(f'<h2>{escape(profile.summary)}</h2><p>Object behavior profile ${profile.index:02X}</p>'
                    '<p>This profile controls the object’s initial movement and animation. Cutscenes can override it through the commands in <b>Event flow</b>.</p>'
                    f'<table cellspacing="0">{fields}</table>'
                    '<h3>How movement works</h3><p>Wandering objects periodically try a random direction. Map bounds, terrain and occupied positions can prevent a step. Stationary objects can still move when an event commands them to.</p>'
                    '<p>These are startup settings, not a simulation of the current game. Event commands refer to runtime slots, which are not necessarily the same as the object numbers in the map list.</p>'
                    f'<h3>Shared profile</h3><p>{escape(uses)}</p>'
                    '<h3>Technical source</h3><p>Local v1.0 loader $01A76C; initial state $01A987; wandering $01AD00; movement $01AC1E; animation $01ADD5. The profile is two packed bytes, not an event bytecode program.</p>')
            self.tabs.addTab(self.behavior,'Movement & behavior')
        if entry is None:
            self.flow.addTopLevelItem(QTreeWidgetItem(["","No verified event entry for this selection. See Details & references.",""]))
            self.raw.setPlainText("No event address was inferred from an unrelated interaction ID.")
        else:
            rows=decode(view_rom(window),entry,extent=extent);partial=any(not r.complete for r in rows)
            self.overview.appendPlainText(f"\nEvent entry: ${entry:06X}\nCoverage: {'Partial — see unexpanded references and explicitly stopped paths' if partial else 'Decoded reachable commands within the inspection limit'}.\nThis is not a full gameplay simulation.")
            old=self.flow;self.tabs.removeTab(1);old.deleteLater()
            self.viewer=EventFlowView(window,entry,extent);self.flow=self.viewer.tree;self.tabs.insertTab(1,self.viewer,'Event flow')
            self.viewer.entryChanged.connect(self.update_raw)
            try:
                length=min(128,0x10000-(entry&0xffff),len(view_rom(window).data)-pc(entry,expanded=True));raw=read(view_rom(window).data,pc(entry,expanded=True),length)
                self.raw.setPlainText("Context bytes only — this is not a verified script length.\n\n"+'\n'.join(f"{entry+i:06X}  {raw[i:i+16].hex(' ').upper()}" for i in range(0,len(raw),16)))
            except ValueError:self.raw.setPlainText("Invalid entry address")
            self.update_raw(entry)
            self.tabs.setCurrentIndex(1)
            self.update_runtime(entry)
            self.viewer.entryChanged.connect(self.update_runtime)
            self.summary=QTextBrowser();self.tabs.addTab(self.summary,'Summary')
            self.update_summary(entry);self.viewer.entryChanged.connect(self.update_summary)
            guide=QPushButton('Explain flags in this event…');guide.clicked.connect(self.show_flag_guide);box.addWidget(guide)
        close=QPushButton("Close");close.clicked.connect(self.close);box.addWidget(close)

    def update_runtime(self,entry):
        from .runtime_inspector import RuntimeInspector
        old=getattr(self,'runtime',None)
        index=self.tabs.indexOf(old) if old is not None else self.tabs.count()
        current=self.tabs.currentWidget() is old if old is not None else False
        if old is not None:self.tabs.removeTab(index);old.deleteLater()
        self.runtime=RuntimeInspector(self.window,entry,self.viewer.extent,self.inspect_runtime_target)
        self.tabs.insertTab(index,self.runtime,'Runtime context')
        if current:self.tabs.setCurrentWidget(self.runtime)

    def update_summary(self,entry):
        from .event_summary import summarize
        summary=summarize(view_rom(self.window),entry,self.viewer.extent)
        sections=[('On entry',summary.opening),('Possible actions',summary.possible),('Conditions checked',summary.conditions),('What this summary can tell you',summary.notes)]
        html=f'<h2>Event ${entry:06X}</h2><p>On-entry actions precede the first branch or unexpanded call. Possible actions include called routines and alternative paths.</p>'
        for title,lines in sections:
            if lines:html+='<h3>'+title+'</h3><ul>'+''.join('<li style="margin-bottom:10px">'+escape(line).replace('\n','<br>')+'</li>' for line in lines)+'</ul>'
        self.summary.setHtml(html)

    def show_flag_guide(self):
        from .event_browser import EventBrowser
        from .event_flags import flag_uses
        browser=getattr(self.window,'event_browser',None)
        if browser is None:
            browser=EventBrowser(self.window);self.window.event_browser=browser
        if browser.stale or browser.project is not self.window.project or browser.snapshot_edits!=self.window.project.edits:browser.refresh()
        browser.show_flags()
        uses=[u for r in decode(view_rom(self.window),self.viewer.entry,limit=4096,extent=self.viewer.extent) for u in flag_uses(r)]
        if uses:
            group=browser.flag_browser.groups[uses[0].flag]
            browser.flag_browser.tree.setCurrentItem(group);browser.flag_browser.tree.scrollToItem(group)

    def inspect_runtime_target(self,target):
        self.tabs.setCurrentWidget(self.viewer);self.viewer.navigate(target)

    def update_raw(self,entry):
        from .events import fragments
        try:
            extent=dict(fragments(view_rom(self.window))).get(entry)
            if self.viewer.extent is not None:extent=self.viewer.extent
            length=min(extent if extent is not None else 128,0x10000-(entry&0xffff),len(view_rom(self.window).data)-pc(entry,expanded=True))
            raw=read(view_rom(self.window).data,pc(entry,expanded=True),length)
            self.raw.setPlainText(f'Current event ${entry:06X}. '+('Bounded text/event extent.' if extent is not None else 'Context bytes only; not a verified script extent.')+'\n\n'+'\n'.join(f'{entry+i:06X}  {raw[i:i+16].hex(" ").upper()}' for i in range(0,len(raw),16)))
        except ValueError:self.raw.setPlainText('Invalid event address')

def open_object(window,index):
    p=window.project;area=view_rom(window).areas[window.area_id];objects=p.objects(area.id)
    if not 0<=index<len(objects):return
    obj=objects[index];kind=(obj[5]>>3)&3;offset=area.offset+8+index*7
    lines=[f"Area ${area.id:02X} — {area.name}",f"Object ${index:02X}; ROM file offset ${offset:06X}",f"Raw record: {obj.hex(' ').upper()}",""]
    if index>=len(area.objects):lines[1]=f'Object ${index:02X}; expanded record, physical location assigned on export'
    for name,(byte,mask,shift) in FIELDS.items():
        value=((obj[2]&192)>>1)|(obj[4]&31) if name=='Behavior index' else (obj[byte]&mask)>>shift
        lines.append(f"{name}: {value} (${value:02X})")
    lines.append("\nVisible under preview flags: "+str(obj[0] in p.flags))
    refs=view_rom(window).object_references[offset] if index<len(area.objects) else [(a.id,index) for a in view_rom(window).areas if a.offset==area.offset]
    lines.append(("Shared physical record references: " if index<len(area.objects) else "Expanded object references: ")+', '.join(f"area ${a:02X}/object ${i:02X}" for a,i in refs))
    entry=None
    if kind==2 and obj[1]<251:
        reward=p.fixed('treasure',obj[1])[0];name=ITEM_NAMES[reward] if reward<64 else {221:'Bomb refill',222:'Projectile refill'}.get(reward,'Unknown')
        lines.append(f"\nChest reward ${obj[1]:02X}: {name}. Quantity/persistence are script-controlled.")
        entry=0x038686
    elif kind==1 and obj[1]<207:
        lines.append(f"\nEncounter group ${obj[1]:02X}. The game chooses among these variants:")
        for i,fid in enumerate(p.fixed('encounter',obj[1])):
            formation=p.fixed('formation',fid)
            names=[enemy_name(window.project,v&127) for v in formation[:3] if v!=255]
            lines.append(f"Variant {i+1}, formation ${fid:02X}: "+' + '.join(names))
        lines.append("Battle interaction is native engine dispatch; an encounter ID is not a script ID.")
    elif kind==0:
        # Exact local interaction caller and table operand, not the upstream
        # v1.1 table at $03D5E5.
        if read(view_rom(window).data,pc(0x01E0F5),11)==bytes.fromhex('ade6198d200022599b00ab') and read(view_rom(window).data,pc(0x009B96),4)==bytes.fromhex('bf36d603'):
            entry=npc_entry(view_rom(window),obj[1])
            if entry is None:lines.append('This reference is outside the verified 124-entry NPC table; no script address is inferred.')
            lines.append(f"\nInteraction event/text reference ${obj[1]:02X}; local pointer table $03D636. See Movement & behavior for the separate native profile.")
    else:lines.append("\nThis interaction class is not yet traced by the inspector; no address is guessed.")
    profile=object_behavior(view_rom(window),obj)
    uses=[]
    if profile is not None:
        for a in view_rom(window).areas:
            for i,other in enumerate(p.objects(a.id)):
                if ((other[2]&192)>>1)|(other[4]&31)==profile.index:
                    uses.append(f'{a.name} / area ${a.id:02X}, object ${i:02X}')
    use_text=f'{len(uses)} area/object references in this project. '+ '; '.join(uses)
    show(window,f"{area.name} · Object ${index:02X}",'\n'.join(lines),entry,(profile,use_text))

def open_connection(window):
    e=window.connection_panel.entry()
    if e is None:return
    text=f"Area ${window.area_id:02X} — {view_rom(window).areas[window.area_id].name}\n{e.label}\nSource: ({e.x}, {e.y})\nAction ${e.action:02X}, ID ${e.value:02X}\nSource ROM offset: {('expanded coordinate; assigned on export' if e.source>=0x200000 else '$%06X'%e.source) if e.source is not None else 'none'}\n"
    if e.target:
        a,x,y,f=e.target;text+=f"\nCurrent-preview destination: ${a:02X} {view_rom(window).areas[a].name}, ({x},{y}), facing {f}\n"
    else:text+='\nDestination depends on runtime state or is unresolved.\n'
    entry=world_entry(view_rom(window),e.value) if e.action==8 else None
    if entry is None:text+='\nThis selection uses field action dispatch rather than a verified script entry.\n'
    key=window.connection_panel.destination_key(e)
    if key is not None:
        location=f'Expanded destination ${e.value:02X}' if key>=0x210000 else f'Shared destination record at ROM ${key:06X}'
        text+='\n'+location+': '+window.project.fixed('destination',key).hex(' ').upper()+'\nOther entrances may use the same record.\n'
    text+='\nPreview flags: '+', '.join(flag_label(f) for f in sorted(window.project.flags))
    show(window,"Entrance / exit inspector",text,entry)

def show(window,title,text,entry,behavior=None):
    # One modeless window per main window; never blocks painting or project saves.
    old=getattr(window,'event_inspector',None)
    if old is not None:old.close();old.deleteLater()
    window.event_inspector=EventInspector(window,title,text,entry,behavior)
    window.event_inspector.show()

