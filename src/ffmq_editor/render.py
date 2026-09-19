"""Static terrain rendering from the verified FFMQ tile-loading routines."""
from functools import lru_cache
import numpy as np
from .rom import pc, read, decode_rle
from .sprites import Sprites
from .animation import Animation

def color_rgb(value):
    return tuple(((value >> shift) & 31)*255//31 for shift in (0,5,10))

def decode_3bpp(raw):
    pixels = np.zeros((8,8), dtype=np.uint8)
    for y in range(8):
        for x in range(8):
            bit = 7-x
            pixels[y,x] = ((raw[y*2] >> bit)&1) | (((raw[y*2+1]>>bit)&1)<<1) | (((raw[16+y]>>bit)&1)<<2)
    return pixels

class Renderer:
    def __init__(self, rom):
        self.rom = rom
        self.sprites = Sprites(rom)
        self.animation = Animation(rom)

    @lru_cache(maxsize=44)
    def graphics(self, attributes_id):
        tiles = np.zeros((256,8,8),dtype=np.uint8)
        palettes = np.zeros(256,dtype=np.uint8)
        attr = self.rom.attributes[attributes_id]
        for group, selector in enumerate(attr.raw[2:10]):
            if selector & 0x80:
                continue
            source = pc(0x058C80)+selector*0x300
            packed = read(self.rom.data, pc(0x05F280)+selector*16,16)
            for tile in range(32):
                tiles[group*32+tile] = decode_3bpp(read(self.rom.data, source+tile*24,24))
                palettes[group*32+tile] = (packed[tile//2] >> (4*(tile&1))) & 7
        return tiles, palettes

    def project_graphics(self, project, attributes_id):
        tiles,palettes=self.graphics(attributes_id)
        changed={resource for kind,resource,_ in project.edits if kind=='terrain_graphic'}
        if not changed:return tiles,palettes
        tiles=tiles.copy();attr=self.rom.attributes[attributes_id]
        for slot,selector in enumerate(attr.raw[2:10]):
            if selector&128:continue
            for t in range(32):
                resource=selector*32+t
                if resource in changed:tiles[slot*32+t]=decode_3bpp(project.fixed('terrain_graphic',resource))
        return tiles,palettes

    def metatiles(self, project, area_id, flags=None, frame=0):
        area = self.rom.areas[area_id]
        attr = self.rom.attributes[area.attributes_id]
        state = project.state(area_id, flags)
        tiles, tile_palettes = self.project_graphics(project,area.attributes_id)
        tiles=self.animation.graphics(area_id,tiles,frame)
        graphics = np.frombuffer(project.fixed("metatile_graphics",project.tileset(area_id)),dtype=np.uint8).reshape(128,4).copy()
        bits = np.frombuffer(project.fixed("metatile_attributes",project.tileset(area_id)),dtype=np.uint8).copy()
        properties = np.frombuffer(project.fixed("properties",project.tileset(area_id)),dtype=np.uint8).reshape(128,2).copy()
        for destination, source in state.remaps:
            graphics[destination] = graphics[source]
            bits[destination] = bits[source]
            properties[destination] = properties[source]
        palette_values=list(project.palette(state.palette))
        for index,value in self.animation.palette(area_id,frame).items():palette_values[56+index]=value
        colors = np.array([color_rgb(v) for v in palette_values],dtype=np.uint8).reshape(8,8,3)
        # Assemble all four quadrants together; no Python loop per metatile.
        pixels=tiles[graphics]
        flips=(bits[:,None] & (1 << np.arange(4)))!=0
        pixels=np.where(flips[:,:,None,None],pixels[:,:,:,::-1],pixels)
        palettes=np.where((bits[:,None]&128)!=0,(bits[:,None]>>4)&7,tile_palettes[graphics])
        quadrants=np.empty((128,4,8,8,4),dtype=np.uint8)
        quadrants[:,:,:,:,:3]=colors[palettes[:,:,None,None],pixels]
        quadrants[:,:,:,:,3]=np.where(pixels==0,0,255)
        atlas=quadrants.reshape(128,2,2,8,8,4).transpose(0,1,3,2,4,5).reshape(128,16,16,4).copy()
        return atlas, properties, state

    @staticmethod
    def tilemap(atlas, cells):
        height,width=cells.shape
        return atlas[cells&127].transpose(0,2,1,3,4).reshape(height*16,width*16,4).copy()

    def has_shifted_overlay(self,area_id):
        area=self.rom.areas[area_id]
        index=((area.header[5]&224)>>2)|((area.header[6]&224)>>5)
        if not index:return False
        mode,graphic,dx,dy=read(self.rom.data,pc(0x0B844F)+(index-1)*4,4)
        return (mode&7)==1 and not(graphic&128) and bool(dx or dy) and ((mode>>4)&7) in (2,4,5,6)

    def terrain_sources(self,area_id,atlas,state,backgrounds=True):
        """Screen-cell to stored-cell ownership for the rendered terrain copy.

        A partially transparent foreground tile still owns its whole metatile:
        painting is a cell operation, not a per-pixel operation.
        """
        area=self.rom.areas[area_id];attrs=self.rom.attributes[area.attributes_id]
        sources=np.arange(attrs.width*attrs.height).reshape(attrs.height,attrs.width)
        if not backgrounds or not self.has_shifted_overlay(area_id):return sources.ravel()
        index=((area.header[5]&224)>>2)|((area.header[6]&224)>>5)
        _,_,dx,dy=read(self.rom.data,pc(0x0B844F)+(index-1)*4,4)
        dx=dx if dx<128 else dx-256;dy=dy if dy<128 else dy-256
        shifted=np.roll(sources,(-dy,-dx),(0,1))
        cells=np.frombuffer(state.cells,dtype=np.uint8)[shifted]
        displayed=np.where(cells&128,0,cells)&127
        opaque=np.any(atlas[:,:,:,3]!=0,axis=(1,2))[displayed]
        return np.where(opaque,shifted,sources).ravel()

    def background(self, area_id, flags, atlas, cells, frame=0):
        area=self.rom.areas[area_id]
        index=((area.header[5]&224)>>2)|((area.header[6]&224)>>5)
        if not index:return None,0
        mode,graphic,p1,p2=read(self.rom.data,pc(0x0B844F)+(index-1)*4,4)
        kind=mode&7
        if kind==1:
            if graphic&128:
                source=0x07F6D1 if 3 in flags else 0x07F538 if 2 in flags else 0x07F37C if 1 in flags else 0x07F240
                raw=decode_rle(self.rom.data,pc(source))
                # RLE layouts use the primary map's dimensions and indexing.
                bgcells=np.frombuffer(raw,dtype=np.uint8).reshape(cells.shape)
            else:
                # Same-map duplication with a signed metatile displacement.
                dx=p1 if p1<128 else p1-256;dy=p2 if p2<128 else p2-256
                bgcells=np.roll(cells,(-dy,-dx),(0,1))
        elif kind in (2,6):
            raw=self.rom.layouts[graphic&63].cells
            bgcells=np.frombuffer(raw[:1024],dtype=np.uint8).reshape(32,32)
        else:
            bgcells=np.array([[graphic&127]],dtype=np.uint8)
        if kind==1:
            # The background caller selects pass zero. Opposite-pass cells
            # are substituted with metatile zero by $01:FCB9.
            bgcells=np.where(bgcells&128,0,bgcells).astype(np.uint8)
        image=self.tilemap(atlas,bgcells)
        h,w=cells.shape[0]*16,cells.shape[1]*16
        yy,xx=np.indices((h,w))
        if kind in (2,6):
            # A fixed camera-origin preview of the half-speed parallax layer.
            yy=(yy+(p1 if p1<128 else p1-256));xx=xx
        if kind==4 and p1:
            direction=read(self.rom.data,pc(0x0B8659)+(p2&3)*4,4)
            dx=int.from_bytes(direction[:2],"little",signed=True);dy=int.from_bytes(direction[2:],"little",signed=True)
            xx=xx+dx*(frame//p1);yy=yy+dy*(frame//p1)
        elif kind==6:
            # $01:FF1F initializes diagonal scrolling to (+4,-1), every
            # three or six ticks depending on flag E4.
            steps=frame//(6 if 0xE4 in flags else 3)
            xx=xx+steps*4;yy=yy-steps
        return image[yy%image.shape[0],xx%image.shape[1]],(mode>>4)&7

    def area(self, project, area_id, flags=None, *, backgrounds=True, sprites=True, show_hidden=False, frame=0):
        frame=max(0,int(frame))
        atlas, properties, state = self.metatiles(project,area_id,flags,frame)
        area = self.rom.areas[area_id]
        attrs = self.rom.attributes[area.attributes_id]
        cells = np.frombuffer(state.cells[:attrs.width*attrs.height],dtype=np.uint8).reshape(attrs.height,attrs.width)
        rgba = self.tilemap(atlas,cells)
        flags=project.flags if flags is None else flags
        bg,blend=self.background(area_id,flags,atlas,cells,frame) if backgrounds else (None,0)
        if bg is not None:
            if blend in (2,4,5,6):
                mask=bg[:,:,3]!=0
                if blend in (5,6):rgba[:,:,:3]//=2
                rgba[mask]=bg[mask]
            else:
                if blend==3:bg[:,:,:3]//=2
                empty=rgba[:,:,3]==0
                rgba[empty]=bg[empty]
        rgba[rgba[:,:,3]==0,:3] = color_rgb(project.palette(state.palette)[0])
        rgba[:,:,3] = 255
        if sprites:
            from .landmarks import records as landmark_records
            foreground=bg[:,:,3]!=0 if bg is not None and blend in (2,4,5,6) else None
            self.sprites.draw(rgba,area_id,flags,show_hidden,foreground,2 if blend in (2,6) else 3,
                              frame,self.animation.palette(area_id,frame,True),project.objects(area_id),landmark_records(project))
        return rgba, atlas, properties, state

def qimage(array):
    from PySide6.QtGui import QImage
    array = np.ascontiguousarray(array,dtype=np.uint8)
    h,w,_ = array.shape
    return QImage(array.data,w,h,w*4,QImage.Format.Format_RGBA8888).copy()
