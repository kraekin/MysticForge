"""Atomic terrain selections and reusable, tileset-compatible stamps."""
from dataclasses import dataclass
import json
from pathlib import Path
from .project import atomic_write


@dataclass(frozen=True)
class Stamp:
    width:int
    height:int
    cells:bytes
    signature:tuple

    @staticmethod
    def profile(rom,area_id):
        attrs=rom.attributes[rom.areas[area_id].attributes_id]
        return (attrs.tileset,*attrs.raw[2:10])

    def save(self,path):
        atomic_write(Path(path),(json.dumps({"format":"ffmq-terrain-stamp","version":1,
                    "width":self.width,"height":self.height,"cells":list(self.cells),"signature":list(self.signature)},indent=2)+"\n").encode())

    @classmethod
    def load(cls,path):
        path=Path(path)
        if path.stat().st_size>100000:raise ValueError("Stamp file is too large")
        data=json.loads(path.read_text())
        if not isinstance(data,dict) or data.get("format")!="ffmq-terrain-stamp" or data.get("version")!=1:raise ValueError("Unsupported stamp")
        width,height=data.get("width"),data.get("height")
        cells,signature=data.get("cells"),data.get("signature")
        if any(type(v) is not int or not 1<=v<=64 for v in (width,height)):raise ValueError("Invalid stamp dimensions")
        if not isinstance(cells,list) or len(cells)!=width*height or any(type(v) is not int or not 0<=v<=255 for v in cells):raise ValueError("Invalid stamp cells")
        if not isinstance(signature,list) or len(signature)!=9 or any(type(v) is not int or not 0<=v<=255 for v in signature):raise ValueError("Invalid stamp tileset")
        return cls(width,height,bytes(cells),tuple(signature))


class Selection:
    def __init__(self,window):
        self.window=window;self.rect=None;self.stamp=None;self.anchor=None;self.moving=None

    def reset(self):self.rect=None;self.anchor=None;self.moving=None

    def capture(self):
        if not self.rect:raise ValueError("Select a terrain rectangle first")
        w=self.window;x,y,width,height=self.rect;cells=[]
        for dy in range(height):
            for dx in range(width):
                key=w.edit_key(x+dx,y+dy)
                if key is None:raise ValueError("Selection extends outside the selected edit resource")
                cells.append(w.project.get(key))
        return Stamp(width,height,bytes(cells),Stamp.profile(w.rom,w.area_id))

    def paste_changes(self,stamp,x,y):
        w=self.window
        if stamp.signature!=Stamp.profile(w.rom,w.area_id):raise ValueError("Stamp uses different tile graphics/properties. Choose a compatible map.")
        changes={}
        for dy in range(stamp.height):
            for dx in range(stamp.width):
                key=w.edit_key(x+dx,y+dy)
                if key is None:raise ValueError("Stamp does not fit inside the selected edit resource")
                old=w.project.get(key);new=stamp.cells[dy*stamp.width+dx]
                from .terrain_paint import scenery_value
                new=scenery_value(w,old,new)
                if old!=new:changes[key]=(old,new)
        return changes

    def clear_changes(self):
        stamp=self.capture();x,y,_,_=self.rect;w=self.window
        blank=w.brush|(128 if w.layer_bit.isChecked() else 0)
        return self.paste_changes(Stamp(stamp.width,stamp.height,bytes([blank])*len(stamp.cells),stamp.signature),x,y)

    def begin(self,x,y):
        w=self.window;tool=w.tool.currentText()
        if tool=="Select":self.anchor=(x,y);self.rect=(x,y,1,1)
        elif tool=="Stamp":
            if not self.stamp:raise ValueError("Copy a selection or load a stamp first")
            w.commit_changes(self.paste_changes(self.stamp,x,y),"Paste terrain stamp")
            self.rect=(x,y,self.stamp.width,self.stamp.height)
        elif tool=="Move selection":
            if not self.rect:raise ValueError("Select a terrain rectangle first")
            sx,sy,width,height=self.rect
            if not(sx<=x<sx+width and sy<=y<sy+height):raise ValueError("Drag from inside the selected rectangle")
            self.moving=(self.capture(),self.rect,(x,y));self.anchor=(x,y)
        w.refresh_map()

    def drag(self,x,y):
        w=self.window
        if self.moving:
            stamp,rect,anchor=self.moving
            self.rect=(rect[0]+x-anchor[0],rect[1]+y-anchor[1],stamp.width,stamp.height)
        elif self.anchor and w.tool.currentText()=="Select":
            ax,ay=self.anchor;self.rect=(min(ax,x),min(ay,y),abs(x-ax)+1,abs(y-ay)+1)
        w.refresh_map()

    def finish(self):
        if not self.moving:return
        stamp,original,_=self.moving;destination=self.rect;self.moving=None;self.anchor=None
        w=self.window
        try:
            # Validate the entire destination before clearing any source cells.
            destination_changes=self.paste_changes(stamp,*destination[:2])
            self.rect=original;changes=self.clear_changes()
            x,y=destination[:2]
            for dy in range(stamp.height):
                for dx in range(stamp.width):
                    key=w.edit_key(x+dx,y+dy)
                    changes[key]=(w.project.get(key),destination_changes.get(key,(w.project.get(key),w.project.get(key)))[1])
            self.rect=destination
            w.commit_changes({k:v for k,v in changes.items() if v[0]!=v[1]},"Move terrain selection")
        except ValueError as error:
            self.rect=original;w.error(error)
        w.refresh_map()
