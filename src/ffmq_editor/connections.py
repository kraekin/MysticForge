"""Map transition overlays, derived from the field dispatch tables."""
from dataclasses import dataclass
from .rom import pc,read,u16


@dataclass(frozen=True)
class Connection:
    x:int
    y:int
    action:int
    value:int
    target:tuple|None
    source:int|None
    label:str


class Connections:
    # Bases are operands in the local v1.0 loader. Counts are derived from
    # adjacent table boundaries, not from the v1.1 randomizer's constants.
    TABLES={0:(0x05F4A0,(0xF72B-0xF4A0)//3,3),
            1:(0x05F79A,(0xF89C-0xF79A)//3,3),
            2:(0x05F72B,(0xF79A-0xF72B)//3,3),
            4:(0x05F4A0,(0xF72B-0xF4A0)//3,3),
            5:(0x05F72B,(0xF79A-0xF72B)//3,3),
            6:(0x05F89C,(0xF920-0xF89C)//4,4)}

    def __init__(self,rom):
        self.rom=rom;self.project=None;self.records=[]
        pointers=[pc(0x05F9F8)+u16(rom.data,pc(0x05F920)+i*2) for i in range(108)]
        for i,start in enumerate(pointers):
            end=pointers[i+1] if i<107 else pc(0x05FFFF)+1
            entries={}
            for cursor in range(start,end-2,3):
                x,y,value=read(rom.data,cursor,3)
                if y&128:break
                entries.setdefault((x,y),(value,cursor))
            self.records.append(entries)

    def destination(self,action,value,flags=None):
        if flags is None:flags=self.project.flags if self.project else self.rom.initial_flags
        if action==8 and value in (0x4c,0x30,0x20):
            # Verified entry prefixes. Dialogue and later side effects are not
            # simulated; these resolve only the first area transition.
            if value==0x4c:
                address=0x03D0E6;expected=bytes.fromhex("2c0c01")
            elif value==0x30:
                if read(self.rom.data,pc(0x03CEDC),7)!=bytes.fromhex("2e043fcf2c0e01"):return None
                address=0x03CF3F if 4 in flags else 0x03CEE0
                expected=bytes.fromhex("2c0f01" if 4 in flags else "2c0e01")
            else:
                # The key-item test either jumps over a flag-set command or
                # falls through it; both branches reach this same transition.
                if read(self.rom.data,pc(0x03CDCC),11)!=bytes.fromhex("2f050c06d4cd23f22c0d01"):return None
                address=0x03CDD4;expected=bytes.fromhex("2c0d01")
            raw=read(self.rom.data,pc(address),3)
            if raw!=expected:return None
            return self.destination(raw[2],raw[1],flags)
        if (action,value)==(8,8) and 2 in flags:
            if read(self.rom.data,pc(0x03C179),8)==bytes.fromhex("050b0282c12c0901"):
                return self.destination(1,9,flags)
        if (action,value)==(8,0x2e):
            # Only this ROM-verified script is resolved; this is not a general
            # interpreter. $2E tests a flag and $2C submits a field command.
            script=u16(self.rom.data,pc(0x03BBD2)+value*2)
            prefix=read(self.rom.data,pc(0x030000|script),11)
            if prefix!=bytes.fromhex("2e 13 71 ce 2c 00 01 00 2c 01 01"):return None
            branch=int.from_bytes(prefix[2:4],"little") if prefix[1] in flags else script+4
            opcode,target_value,target_action=read(self.rom.data,pc(0x030000|branch),3)
            if opcode!=0x2c or target_action!=1:return None
            return self.destination(target_action,target_value,flags)
        if action not in self.TABLES:return None
        base,count,size=self.TABLES[action]
        if not 0<=value<count:return None
        offset=pc(base)+value*size
        raw=(self.project.fixed("destination",offset) if self.project else read(self.rom.data,offset,size))[-3:]
        area,y,x=raw
        if area>=108:return None
        attrs=self.rom.attributes[self.rom.areas[area].attributes_id]
        if (x&63)>=attrs.width or y>=attrs.height:return None
        return area,x&63,y,(x>>6)&3

    def for_area(self,area_id,state,properties):
        area=self.rom.areas[area_id]
        if area.layout_id==0:
            result=[]
            for node in range(0x16,0x38):
                x,y=self.project.fixed("world_node",node) if self.project else read(self.rom.data,pc(0x07F7C3)+node*2,2)
                source=pc(0x07EFCB)+(node-0x16)*2
                value,action=self.project.fixed("world_action",node) if self.project else read(self.rom.data,source,2)
                label=f"World node ${node:02X}"
                if (action,value)==(8,0x2e):label+=" · Level Forest entry script $2E · flag $13 "+("set" if 0x13 in state.flags else "clear")
                elif action==8:
                    label+=f" · entry script ${value:02X}"
                    if value==0x30:label+=" · flag $04 "+("set" if 4 in state.flags else "clear")
                    if value==8 and 2 not in state.flags:label+=" · item/dialogue context required"
                result.append(Connection(x,y,action,value,self.destination(action,value,state.flags),source,label))
            return tuple(result)
        attrs=self.rom.attributes[area.attributes_id];records=self.records[area_id];result=[]
        if self.project:
            records={}
            for _,offset in self.records[area_id].values():
                rx,ry,rv=self.project.fixed("coordinate",offset)
                records.setdefault((rx,ry),(rv,offset))
        for index,cell in enumerate(state.cells[:attrs.width*attrs.height]):
            prop=int(properties[cell&127,1])
            if prop&0xE0!=0x80:continue
            action=prop&31
            if action>6:continue
            x,y=index%attrs.width,index//attrs.width
            value,source=records.get((x,y),(0,None))
            label="Saved return (runtime position)" if action==3 else "Transition"
            if source is None and action!=3:label+=" · no local coordinate record"
            # The engine scans past pointer boundaries until a negative-Y
            # sentinel. Resolve that fallback only from actual ROM bytes.
            if source is None and action!=3:
                cursor=pc(0x05F9F8)+u16(self.rom.data,pc(0x05F920)+area_id*2)
                while cursor+3<=pc(0x05FFFF)+1:
                    rx,ry,rv=self.project.fixed("coordinate",cursor) if self.project and cursor in self.rom.coordinate_offsets else read(self.rom.data,cursor,3)
                    if (rx,ry)==(x,y):value,source=rv,cursor;break
                    if ry&128:break
                    cursor+=3
            result.append(Connection(x,y,action,value,self.destination(action,value),source,label))
        return tuple(result)

