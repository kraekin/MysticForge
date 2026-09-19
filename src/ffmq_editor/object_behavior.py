"""Read-only object profiles from the local v1.0 loader, not guessed scripts."""
from dataclasses import dataclass
from .rom import pc,read
from .field_actions import DIRECTIONS

PROFILE_BASE=0x0B87E4
PROFILE_COUNT=87  # The next table begins at $0B8892.

@dataclass(frozen=True)
class ObjectBehavior:
    index:int
    raw:bytes
    facing:int

    @property
    def state(self):return self.raw[1]>>6

    @property
    def summary(self):
        return ('Wanders when idle','Starts in a movement state','Stationary','Animates in place')[self.state]

    def fields(self):
        speed=self.raw[0]>>6
        return [
            ('Initial behavior',self.summary),
            ('Stored direction',DIRECTIONS[self.facing]),
            ('Movement speed',f'{(1,2,4,4)[speed]} pixel(s) per object update'),
            ('Animation layout',f'${self.raw[0]&63:02X}'),
            ('Animation frame mask',f'${self.raw[1]&3:02X} (native frame index is ANDed with this value)'),
            ('Sprite position adjustment',f'X +{8 if self.raw[1]&32 else 0} pixels; Y +{8 if self.raw[1]&16 else 0} pixels'),
            ('Alternating sprite adjustment','X: 0/1 pixel' if self.raw[1]&8 else 'Y: 0/1 pixel' if self.raw[1]&4 else 'None'),
            ('Profile bytes',self.raw.hex(' ').upper()),
            ('ROM address',f'${PROFILE_BASE+2*self.index:06X}'),
        ]

def object_behavior(rom,obj):
    index=((obj[2]&192)>>1)|(obj[4]&31)
    if index>=PROFILE_COUNT:return None
    # Exact v1.0 loader operands and bit extraction. Reject unrelated ROM code.
    if read(rom.data,pc(0x01A77D),4)!=bytes.fromhex('bfe4870b'):return None
    return ObjectBehavior(index,read(rom.data,pc(PROFILE_BASE)+index*2,2),(obj[3]>>6)&3)


def compatible_profiles(rom,index):
    """Preserve animation layout, masks and offsets; vary only state/speed."""
    if not 0<=index<PROFILE_COUNT:return ()
    if read(rom.data,pc(0x01A77D),4)!=bytes.fromhex('bfe4870b'):return ()
    base=pc(PROFILE_BASE);original=rom.data[base+2*index:base+2*index+2]
    return tuple(ObjectBehavior(i,rom.data[base+2*i:base+2*i+2],0) for i in range(PROFILE_COUNT)
                 if rom.data[base+2*i]&63==original[0]&63 and rom.data[base+2*i+1]&63==original[1]&63)
