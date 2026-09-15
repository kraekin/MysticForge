"""Place compatible field-object presets through the map canvas."""
import numpy as np
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QListWidgetItem,QLineEdit,QPushButton
from .render import qimage


class ObjectPalette(QWidget):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.window=editor.window;self.signature=None;self.presets=[]
        box=QVBoxLayout(self);note=QLabel('Choose a preset, then click an empty map tile to place one object. Switch to Select / move to drag or edit objects. Escape leaves placement mode.');note.setWordWrap(True);box.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText('Find NPC, chest, encounter or source map…');box.addWidget(self.search)
        self.list=QListWidget();self.list.setViewMode(QListWidget.ViewMode.IconMode);self.list.setResizeMode(QListWidget.ResizeMode.Adjust);self.list.setMovement(QListWidget.Movement.Static);self.list.setWordWrap(True);self.list.setIconSize(QSize(48,48));self.list.setGridSize(QSize(124,100));box.addWidget(self.list,1)
        self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        appearance=QPushButton('Use appearance for selected object');appearance.setToolTip('Copies sprite, colors and animation/movement behavior. Keeps position, visibility and interaction. Shared object records retain their existing scope.');box.addWidget(appearance);appearance.clicked.connect(self.apply_appearance)
        edit=QPushButton('Edit last placed / selected object');edit.clicked.connect(lambda:editor.mode.setCurrentIndex(0));box.addWidget(edit)
        self.list.currentRowChanged.connect(self.describe);self.search.textChanged.connect(self.filter)

    def refresh(self):
        w=self.window;area=w.rom.areas[w.area_id]
        signature=(id(w.project),id(w.renderer),w.area_id,frozenset(w.project.flags),tuple(w.project.objects(w.area_id)))
        if self.signature==signature:return
        self.signature=signature;previous=self.raw();self.list.blockSignals(True);self.list.clear();self.presets=[];seen=set()
        if area.layout_id:
            template=w.project.newmaps.get(area.id,{}).get('source',area.id)
            private=w.project.sprite_sets.get(area.id)
            selector=private['base'] if private else area.header[2]
            candidates=sorted(w.project.base_rom.areas[:108],key=lambda a:a.id!=template)
            sources=[(area,w.project.objects(area.id))]
            if private:sources.append((area,private['presets']))
            sources += [(a,a.objects) for a in candidates if a.header[2]==selector and (private or a.id!=area.id)]
            from .sprite_sets import frames,descriptor,unpack
            from .sprites import Sprites
            original_sprites=Sprites(w.project.base_rom);target_tiles,target_colors=w.renderer.sprites.field_set(area.id)
            for source,objects in sources:
                for index,raw in enumerate(objects):
                    if private and source is not area:
                        src_tiles,src_colors=original_sprites.field_set(source.id)
                        if not all(np.array_equal(src_tiles[t],target_tiles[t]) and np.array_equal(src_colors[(raw[4]>>5)|((attr>>1)&7)],target_colors[(raw[4]>>5)|((attr>>1)&7)]) for t,attr in frames(w.rom,raw)):continue
                    normalized=bytearray(raw);normalized[2]&=192;normalized[3]&=192;key=bytes(normalized)
                    if key in seen:continue
                    seen.add(key);kind=('NPC/event','Encounter','Chest/reward','Special')[((raw[5]>>3)&3)]
                    imported=private and source is area and objects is private['presets']
                    source_label=private['labels'][index] if imported else f'{source.name}, object ${index:02X}'
                    label=f'{kind} ${index:02X}\n'+(private['labels'][index] if imported else source.name)
                    preview=self.preview(raw);icon=QIcon(preview)
                    # Crop transparent padding for a readable thumbnail.
                    pixels=np.zeros((48,48,4),dtype=np.uint8);obj=bytearray(raw);obj[2]=(obj[2]&192)|1;obj[3]=(obj[3]&192)|1
                    w.renderer.sprites.draw(pixels,w.area_id,w.project.flags,True,objects=[bytes(obj)])
                    ys,xs=np.where(pixels[:,:,3])
                    if len(xs):icon=QIcon(QPixmap.fromImage(qimage(pixels[ys.min():ys.max()+1,xs.min():xs.max()+1].copy())).scaled(48,48,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
                    item=QListWidgetItem(icon,label);item.setToolTip(f'{source_label}\nSprite ${raw[6]&127:02X}; interaction class {(raw[5]>>3)&3}, ID ${raw[1]:02X}; visibility ${raw[0]:02X}.\nCopies behavior, interaction and visibility; rewards and encounters remain shared.');self.list.addItem(item);self.presets.append((key,preview))
        chosen=next((i for i,(raw,_) in enumerate(self.presets) if raw==previous),0)
        self.list.setCurrentRow(chosen if self.presets else -1);self.list.blockSignals(False);self.filter();self.describe()

    def apply_appearance(self):
        w=self.window;index=self.editor.selected;raw=self.raw()
        if raw is None or index<0:self.info.setText('Select an existing object first, then choose its appearance here.');return
        from .sprite_sets import appearance
        from .sprite_set_editor import set_object
        set_object(w,index,appearance(w.project.objects(w.area_id)[index],raw),'Choose object appearance')
        self.editor.mode.setCurrentIndex(0)

    def preview(self,raw):
        w=self.window;pixels=np.zeros((48,48,4),dtype=np.uint8);obj=bytearray(raw);obj[2]=(obj[2]&192)|1;obj[3]=(obj[3]&192)|1
        w.renderer.sprites.draw(pixels,w.area_id,w.project.flags,True,objects=[bytes(obj)])
        return QPixmap.fromImage(qimage(pixels))

    def raw(self):
        i=self.list.currentRow()
        return self.presets[i][0] if 0<=i<len(self.presets) else None

    def filter(self,*_):
        text=self.search.text().casefold()
        for i in range(self.list.count()):self.list.item(i).setHidden(text not in self.list.item(i).text().casefold())
        if self.list.currentItem() is None or self.list.currentItem().isHidden():self.list.setCurrentRow(next((i for i in range(self.list.count()) if not self.list.item(i).isHidden()),-1))

    def describe(self,*_):
        self.window.canvas.object_preview=None;self.window.canvas.viewport().update();raw=self.raw()
        if raw is None:self.info.setText('No compatible presets on this map. Overworld landmarks use Artwork.');return
        visible=raw[0] in self.window.project.flags
        self.info.setText(f'Copies interaction ${(raw[1]):02X} and visibility flag ${raw[0]:02X} ({"visible" if visible else "hidden"} in this preview). Behavior, chest rewards and encounters are reused, not newly created. Edit the placed object to change them.')

    def hover(self,x,y):
        w=self.window;a=w.rom.areas[w.area_id];attrs=w.rom.attributes[a.attributes_id];w.canvas.object_preview=None
        if a.layout_id and self.raw() is not None and 0<=x<attrs.width and 0<=y<attrs.height:
            w.canvas.object_preview=(x,y,self.presets[self.list.currentRow()][1])
        w.canvas.viewport().update()

    def place(self,x,y):
        w=self.window;a=w.rom.areas[w.area_id];objects=w.project.objects(w.area_id);raw=self.raw();attrs=w.rom.attributes[a.attributes_id]
        if raw is None or a.layout_id==0 or not (0<=x<attrs.width and 0<=y<attrs.height):return
        if any((o[3]&63,o[2]&63)==(x,y) for o in objects):self.info.setText('An object already occupies this tile. Use Select / move to edit it.');return
        if a.offset not in w.rom.structural_object_sets or len(objects)>=w.project.object_capacity(w.area_id):
            self.info.setText('No free object slots. Expanded export permits up to 16 objects on smaller field maps; shared-tail lists cannot grow.');return
        count=len(objects);obj=bytearray(raw);obj[2]=(obj[2]&192)|y;obj[3]=(obj[3]&192)|x
        changes={w.project.object_key(w.area_id,count,i):(w.project.get(w.project.object_key(w.area_id,count,i)),v) for i,v in enumerate(obj)}
        changes[('object_count',a.offset,0)]=(count,count+1)
        w.commit_changes(changes,'Place object');self.editor.list.setCurrentRow(count)
        self.info.setText(f'Placed object {count:02X} at ({x}, {y}). {count+1}/{w.project.object_capacity(w.area_id)} slots used. '+('Hidden by its copied visibility flag. ' if raw[0] not in w.project.flags else '')+'Click another empty tile to place another, or edit the selected object.')
