"""field-animation previews from the bank 07/0C tables."""
from functools import lru_cache
import numpy as np
from .rom import pc, read, u16


class Animation:
    def __init__(self, rom):
        self.rom=rom

    @lru_cache(maxsize=16)
    def tile_program(self, profile):
        # Profile E is found only in the background-only area records; its
        # table entry is FFFF rather than an executable field animation.
        if not 0<profile<14:return ()
        data=self.rom.data
        cursor=pc(0x0CD500)+u16(data,pc(0x0CD4E4)+profile*2)
        first,second=read(data,cursor,2);cursor+=2
        if first==255:return ()
        destinations=[first+i for i in range(4)]+[second+i for i in range(4)]
        program=[]
        for slot in range(8):
            end=data.index(255,cursor,pc(0x0CD666))
            record=data[cursor:end];cursor=end+1
            if not record:continue
            period,operation=record[:2]
            program.append((destinations[slot],period,operation,tuple(record[3:]) if operation==0 else ()))
        return tuple(program)

    def graphics(self, area_id, tiles, frame):
        if not frame:return tiles
        program=self.tile_program(self.rom.areas[area_id].header[3]>>4)
        if not program:return tiles
        result=tiles.copy()
        for destination,period,operation,sequence in program:
            steps=frame//(period+1)
            if not steps or destination>=256:continue
            if operation==0 and sequence:
                result[destination]=tiles[sequence[steps%len(sequence)]]
            elif operation in (1,2):
                result[destination]=np.roll(tiles[destination],steps*(1 if operation==1 else -1),axis=1)
            elif operation in (3,4):
                result[destination]=np.roll(tiles[destination],steps*(-1 if operation==3 else 1),axis=0)
        return result

    @lru_cache(maxsize=32)
    def palette_program(self, profile, sprites=False):
        data=self.rom.data
        selector=data[pc(0x0CD666)+profile*2+int(sprites)]
        pointers,base=(0x0CD727,0x0CD72F) if sprites else (0x0CD686,0x0CD694)
        cursor=pc(base)+u16(data,pc(pointers)+selector*2)
        programs=[]
        for _ in range(7):
            end=data.index(255,cursor,pc(0x0CD800))
            record=data[cursor:end];cursor=end+1
            programs.append((record[0],tuple(record[2:])) if record else (0,()))
        return tuple(programs)

    def palette(self, area_id, frame, sprites=False):
        area=self.rom.areas[area_id]
        if not frame or not area.header[4]&32:return {}
        result={}
        for color,(period,sequence) in enumerate(self.palette_program(area.header[3]&15,sprites)):
            if sequence:
                steps=frame//max(1,period)
                if steps:
                    # Palette runner reads the current sequence index before incrementing.
                    index=sequence[(steps-1)%len(sequence)]
                    result[color+1]=u16(self.rom.data,pc(0x058A80)+index*2)
        return result
