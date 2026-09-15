"""Map-local sprite choices with visual comparison and separate interactions."""
import numpy as np
from PySide6.QtCore import QSize,Qt
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QListWidget,QListWidgetItem,QPushButton,QTabWidget,QWidget,QLineEdit
from .sprites import Sprites
from .sprite_sets import choose,import_sprite,appearance,interaction,descriptor,unpack
from .expanded_content_editor import commit
from .expansion_editor import snapshot,restore
from .render import qimage

def picture(renderer,area,obj,flags):
    pixels=np.zeros((48,48,4),dtype=np.uint8);raw=bytearray(obj);raw[2]=(raw[2]&192)|1;raw[3]=(raw[3]&192)|1
    renderer.draw(pixels,area,flags,True,objects=[bytes(raw)])
    return pixels

def icon(pixels):
    ys,xs=np.where(pixels[:,:,3])
    if len(xs):pixels=pixels[ys.min():ys.max()+1,xs.min():xs.max()+1].copy()
    return QIcon(QPixmap.fromImage(qimage(pixels)).scaled(48,48,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))

def templates(rom):
    seen=set()
    for a in rom.areas[:108]:
        if not a.layout_id:continue
        for i,o in enumerate(a.objects):
            raw=bytearray(o);raw[2]&=192;raw[3]&=192;key=(a.header[2],bytes(raw))
            if key in seen:continue
            seen.add(key);yield a,i,o

def set_object(w,index,raw,label):
    old=w.project.objects(w.area_id)[index]
    w.commit_changes({w.project.object_key(w.area_id,index,i):(v,raw[i]) for i,v in enumerate(old) if v!=raw[i]},label)

def open_interactions(editor):
    w=editor.window;index=editor.selected;area=w.area_id
    if index<0:return
    d=QDialog(w);d.setWindowTitle('Choose interaction');d.resize(650,600);box=QVBoxLayout(d)
    note=QLabel('Choose an existing interaction. This changes the event, encounter or reward reference without changing the sprite, movement, visibility or position. References remain shared with their source objects.');note.setWordWrap(True);box.addWidget(note)
    search=QLineEdit();search.setPlaceholderText('Find map, event, encounter or reward…');box.addWidget(search);items=QListWidget();box.addWidget(items,1);rows=[];seen=set()
    for a,i,o in templates(w.project.base_rom):
        key=((o[5]>>3)&3,o[1])
        if key in seen:continue
        seen.add(key);kind=('Event','Encounter','Reward','Special')[key[0]];items.addItem(f'{kind} ${key[1]:02X} · {a.name}, object ${i:02X}');rows.append(o)
    def filter_rows(text):
        for i in range(items.count()):items.item(i).setHidden(text.casefold() not in items.item(i).text().casefold())
    search.textChanged.connect(filter_rows);button=QPushButton('Use selected interaction');box.addWidget(button)
    def apply():
        i=items.currentRow()
        if i<0 or items.item(i).isHidden():return
        if w.area_id!=area or index>=len(w.project.objects(area)):w.error('The selected object changed. Reopen this chooser.');return
        set_object(w,index,interaction(w.project.objects(area)[index],rows[i]),'Choose object interaction');d.accept()
    button.clicked.connect(apply);w.interaction_dialog=d;d.setModal(True);d.show()

def open_sprites(w):
    if not w.project.expanded:
        from .expansion_editor import show_expansion
        show_expansion(w);return
    area=w.area_id
    if w.rom.areas[area].layout_id==0:w.error('Overworld landmarks use Artwork. Choose a field map.');return
    d=QDialog(w);d.setWindowTitle(f'Map sprites · {w.rom.areas[area].name}');d.resize(820,700);root=QVBoxLayout(d)
    note=QLabel('Changes apply only to this map configuration. Terrain and interactions stay intact. Replacing a complete set can change existing objects’ appearance; review the comparison before applying.');note.setWordWrap(True);root.addWidget(note)
    tabs=QTabWidget();root.addWidget(tabs,1);whole=QWidget();box=QVBoxLayout(whole);tabs.addTab(whole,'Choose sprite set')
    sets=QComboBox();seen=set()
    for a in w.project.base_rom.areas:
        selector=a.header[2]
        if not a.layout_id or selector==255 or selector in seen:continue
        seen.add(selector);sets.addItem(f'{a.name} · sprite set ${selector:02X}',a.id)
    current=w.project.sprite_sets.get(area,{}).get('base',w.rom.areas[area].header[2])
    sets.setCurrentIndex(next((i for i in range(sets.count()) if w.project.base_rom.areas[sets.itemData(i)].header[2]==current),0))
    box.addWidget(sets);compare=QListWidget();compare.setIconSize(QSize(96,48));box.addWidget(compare,1);status=QLabel();status.setWordWrap(True);box.addWidget(status)
    use=QPushButton('Use this sprite set for this map');box.addWidget(use)
    def preview():
        compare.clear();before=snapshot(w.project);objects=w.project.objects(area);old=Sprites(w.rom)
        try:
            choose(w.project,area,sets.currentData());new=Sprites(w.project.rom);changed=0
            for i,o in enumerate(objects):
                a=picture(old,area,o,w.project.flags);b=picture(new,area,o,w.project.flags);different=not np.array_equal(a,b);changed+=different
                pix=QPixmap(96,48);pix.fill(Qt.GlobalColor.transparent);paint=QPainter(pix);paint.drawPixmap(0,0,icon(a).pixmap(48,48));paint.drawPixmap(48,0,icon(b).pixmap(48,48));paint.end()
                label='blank in initial pose after change' if a[:,:,3].any() and not b[:,:,3].any() else 'appearance changes' if different else 'same initial appearance'
                compare.addItem(QListWidgetItem(QIcon(pix),f'Object ${i:02X} · '+label+' · before → after'))
            status.setText(f'{changed}/{len(objects)} initial appearances change. Comparison shows the current preview flags and initial pose; scripted movement and palette animation are not simulated here. Empty maps receive the new palette without adding objects.')
        except ValueError as e:status.setText(str(e))
        finally:restore(w.project,before)
    sets.currentIndexChanged.connect(preview);preview()
    def apply_set():
        if w.area_id!=area:return
        if commit(w,lambda:choose(w.project,area,sets.currentData()),'Choose map sprite set'):w.object_editor.mode.setCurrentIndex(1);w.object_editor.palette.search.clear();d.accept()
    use.clicked.connect(apply_set)
    single=QWidget();box=QVBoxLayout(single);tabs.addTab(single,'Add individual sprite');search=QLineEdit();search.setPlaceholderText('Find a source map or object type…');box.addWidget(search)
    gallery=QListWidget();gallery.setViewMode(QListWidget.ViewMode.IconMode);gallery.setResizeMode(QListWidget.ResizeMode.Adjust);gallery.setMovement(QListWidget.Movement.Static);gallery.setIconSize(QSize(48,48));gallery.setGridSize(QSize(160,95));gallery.setWordWrap(True);box.addWidget(gallery,1)
    rows=list(templates(w.project.base_rom));renderer=Sprites(w.project.base_rom)
    for a,i,o in rows:
        kind=('NPC/event','Encounter','Chest/reward','Special')[(o[5]>>3)&3];item=QListWidgetItem(icon(picture(renderer,a.id,o,w.project.flags)),f'{kind} ${i:02X}\n{a.name}');item.setToolTip(f'{a.name}, object ${i:02X}. Imports appearance and makes its original interaction available as a preset.');gallery.addItem(item)
    feedback=QLabel('Choose a sprite to add to the placement palette. The allocator checks all existing objects and imported presets. Incompatible shared monster/boss sheets or exhausted slots produce an explanation.');feedback.setWordWrap(True);box.addWidget(feedback)
    def filtering(text):
        for i in range(gallery.count()):gallery.item(i).setHidden(text.casefold() not in gallery.item(i).text().casefold())
    search.textChanged.connect(filtering)
    add=QPushButton('Add selected sprite to this map’s palette');box.addWidget(add)
    def add_sprite():
        i=gallery.currentRow()
        if i<0 or gallery.item(i).isHidden() or w.area_id!=area:return
        a,_,o=rows[i];result=[]
        if commit(w,lambda:result.append(import_sprite(w.project,area,a.id,o)),'Import map sprite'):
            w.object_editor.mode.setCurrentIndex(1);p=w.object_editor.palette;p.refresh();p.search.clear()
            raw=bytearray(result[0]);raw[2]&=192;raw[3]&=192
            p.list.setCurrentRow(next((j for j,(r,_) in enumerate(p.presets) if r==bytes(raw)),0));d.accept()
    add.clicked.connect(add_sprite)
    imported=QWidget();box=QVBoxLayout(imported);tabs.addTab(imported,'Imported presets')
    note=QLabel('Imported presets reserve graphics and colors for future placement. Removing a preset releases that reservation; objects already placed remain intact and continue protecting their graphics.');note.setWordWrap(True);box.addWidget(note)
    saved=QListWidget();box.addWidget(saved,1)
    for i,o in enumerate(w.project.sprite_sets.get(area,{}).get('presets',[])):
        saved.addItem(QListWidgetItem(icon(picture(w.renderer.sprites,area,o,w.project.flags)),w.project.sprite_sets[area]['labels'][i]+f' · local sprite ${o[6]&127:02X}'))
    remove=QPushButton('Remove selected preset');box.addWidget(remove)
    def remove_preset():
        i=saved.currentRow()
        if i<0 or w.area_id!=area:return
        if commit(w,lambda:(w.project.sprite_sets[area]['presets'].pop(i),w.project.sprite_sets[area]['labels'].pop(i)),'Remove imported sprite preset'):d.accept()
    remove.clicked.connect(remove_preset);w.sprite_dialog=d;d.setModal(True);d.show()
