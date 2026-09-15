"""Field OBJ graphics and initial poses, decoded from the exact ROM's loaders.

This is a map preview, not an event VM: saved enemy/chest state and scripted
movement are not synthesized. Coordinates use the initial area records.
"""
from functools import lru_cache
import numpy as np
from .rom import pc, read, u16


class Sprites:
    def __init__(self, rom):
        self.rom = rom

    @lru_cache(maxsize=256)
    def tile(self, address):
        from .render import decode_3bpp
        return decode_3bpp(read(self.rom.data, pc(address), 24))

    def colors(self, ids):
        from .render import color_rgb
        return np.array([[color_rgb(u16(self.rom.data, pc(0x07D824)+p*16+i*2))
                          for i in range(8)] for p in ids], dtype=np.uint8)

    @lru_cache(maxsize=108)
    def field_set(self, area_id):
        data = self.rom.data
        selector = self.rom.areas[area_id].header[2]
        tiles = np.zeros((512,8,8),dtype=np.uint8)
        palette_ids = [0]*8
        palette_ids[6] = 1
        if selector == 255:
            return tiles, self.colors(palette_ids)
        descriptor = pc(0x0B88FC)+u16(data,pc(0x0B8892)+selector*2)
        palette_ids[:6] = read(data,descriptor,6)

        def load(source, destination, count):
            for i in range(count):
                tiles[destination+i] = self.tile(source+i*24)

        # Common chests/boxes: buffer $0000 -> VRAM $6900 -> OBJ tile $90.
        load(0x04E520,0x90,16)
        # 44 presence bits, followed by one graphics selector for each set bit.
        cursor = descriptor+12
        for slot in range(44):
            if data[descriptor+6+slot//8] & (0x80>>(slot%8)):
                graphic = data[cursor]; cursor += 1
                destination = 0x90+u16(data,pc(0x01A5DF)+slot*2)//32
                source = 0x04D7A0+(graphic&127)*96 if graphic&128 else 0x049A20+graphic*384
                # $FF entries select a non-ROM range in the vanilla loader;
                # preserve the cleared slot rather than decode unrelated bytes.
                if graphic!=255:load(source,destination,8 if graphic&128 else 16)
        # The shared monster sheet occupies the tail unless the descriptor
        # requests the special boss sheet (loaded separately according to F2).
        if not data[descriptor+11]&1:
            load(0x04ADA0,0x180,96)
        # The hero/companion slots preceding $90 are filled by other loaders.
        load(0x049A20,0x10,16)
        load(0x04CA20,0x20,80)
        return tiles,self.colors(palette_ids)

    @lru_cache(maxsize=1)
    def world_set(self):
        data = self.rom.data
        tiles = np.zeros((512,8,8),dtype=np.uint8)
        cursor=pc(0x01E95D); dest=0x100
        while data[cursor]!=255:
            value=data[cursor];cursor+=1
            pixels=self.tile(0x04F5A0+(value&63)*24)
            if value&64:pixels=pixels[::-1,:]
            if value&128:pixels=pixels[:,::-1]
            tiles[dest]=pixels;dest+=1
        for i in range(136):tiles[0x160+i]=self.tile(0x07DDC4+i*24)
        for i in range(8):tiles[0x1F0+i]=self.tile(0x07DDC4+(136+i)*24)
        return tiles,self.colors([0x37,0x38,0x39,0x3C,0x3B,0x3A,0x3D,0])

    @staticmethod
    def paint_tile(canvas, pixels, colors, x, y, occlusion=None):
        h,w=canvas.shape[:2]
        left,top=max(x,0),max(y,0);right,bottom=min(x+8,w),min(y+8,h)
        if left>=right or top>=bottom:return
        crop=pixels[top-y:bottom-y,left-x:right-x]
        target=canvas[top:bottom,left:right]
        mask=crop!=0
        if occlusion is not None:mask &= ~occlusion[top:bottom,left:right]
        target[mask,:3]=colors[crop[mask]];target[mask,3]=255

    def draw(self, canvas, area_id, flags, show_hidden=False, foreground=None, field_priority=3, frame=0, palette_changes=None, objects=None):
        data=self.rom.data;area=self.rom.areas[area_id]
        if area.layout_id==0:
            tiles,colors=self.world_set()
            cursor=pc(0x07EB44)
            while data[cursor]<128:
                y,x,flag,tile,attr=read(data,cursor,5);cursor+=5
                if flag and flag not in flags and not show_hidden:continue
                # These are 16x16 hardware OBJs; row stride is 16 tiles.
                base=tile+((attr&1)<<8)
                for q in range(4):
                    dx,dy=q%2,q//2
                    sx=1-dx if attr&64 else dx;sy=1-dy if attr&128 else dy
                    pixels=tiles[(base+sx+sy*16)&511]
                    if attr&64:pixels=pixels[:,::-1]
                    if attr&128:pixels=pixels[::-1,:]
                    self.paint_tile(canvas,pixels,colors[(attr>>1)&7],x*16+dx*8,y*16+dy*8,
                                    foreground if ((attr>>4)&3)<3 else None)
            return
        tiles,colors=self.field_set(area_id)
        if palette_changes:
            from .render import color_rgb
            colors=colors.copy()
            for index,value in palette_changes.items():colors[5,index]=color_rgb(value)
        selector=area.header[2]
        if selector!=255:
            descriptor=pc(0x0B88FC)+u16(data,pc(0x0B8892)+selector*2)
            if data[descriptor+11]&1 and 0xF2 not in flags:
                tiles=tiles.copy()
                for i in range(128):tiles[0x180+i]=self.tile(0x04BE20+i*24)
        # Stable coordinate order approximates overlapping objects' depth.
        for obj in sorted(area.objects if objects is None else objects,key=lambda o:o[2]&63):
            if obj[0] not in flags and not show_hidden:continue
            behavior=((obj[2]&192)>>1)|(obj[4]&31)
            b0,b1=read(data,pc(0x0B87E4)+behavior*2,2)
            animation=b0&63
            facing=(obj[3]>>6)* (16 if animation<5 else 8)
            pose=0
            if b1>>6==2:
                speed=b0>>6
                period=16 if speed==0 else 8 if speed==1 else 2
                pose=(frame//period)&(b1&3)
            frame_address=pc(0x00F141)+u16(data,pc(0x00FDCF)+animation*2)+facing+pose*8
            x=(obj[3]&63)*16+(8 if b1&32 else 0)
            y=(obj[2]&63)*16-8+(8 if b1&16 else 0)
            if b1&8:x+=pose&1
            if b1&4:y+=pose&1
            for q in range(4):
                tile,attr=read(data,frame_address+q*2,2)
                tile=(tile+(obj[6]&127)*4+((attr&1)<<8))&511
                pixels=tiles[tile]
                if attr&64:pixels=pixels[:,::-1]
                if attr&128:pixels=pixels[::-1,:]
                palette=(((obj[4]>>4)|attr)>>1)&7
                self.paint_tile(canvas,pixels,colors[palette],
                                x+(q%2)*8,y+(q//2)*8,foreground if field_priority<3 else None)
