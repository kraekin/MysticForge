"""Opt-in 1 MiB LoROM profile. Only the appended half is newly owned storage."""
from .rom import pc,FormatError
from .layout_storage import LayoutPlan,PoolBudget,compressed,cpu_address,POINTERS

BASE_SIZE=0x80000
EXPANDED_SIZE=0x100000
TABLE=BASE_SIZE
TABLE_SIZE=64*3
LOADERS=(0x0b852b,0x0b861a)

def verify_profile(rom):
    if len(rom.data)!=BASE_SIZE or rom.data[0x7fd5]!=0x20 or rom.data[0x7fd7]!=9:
        raise FormatError('ROM does not match the verified 512 KiB LoROM expansion profile')
    # Catch extra known-form consumers instead of silently leaving an old table user.
    for delta in (0,2):
        pattern=b'\xbf'+(0x0b8735+delta).to_bytes(3,'little')
        actual={i for i in range(len(rom.data)) if rom.data.startswith(pattern,i)}
        expected={pc(a)+(0 if delta==0 else 9) for a in LOADERS}
        if actual!=expected:raise FormatError('Unexpected layout pointer-table consumer')
    expected=bytes.fromhex('a600e8e88a1867008506e220a502851b48aba505851a85208521a403640d')
    if rom.data[pc(0x0b867e):pc(0x0b867e)+len(expected)]!=expected:
        raise FormatError('Decompressor bank setup does not match expansion profile')

def plan_expanded(project):
    rom=project.rom;verify_profile(rom)
    from .expanded_content import active,writes as content_writes
    from .world_expansion import active as world_active,writes as world_writes
    from .new_maps import writes as map_writes
    from .sprite_sets import writes as sprite_writes
    from .landmarks import writes as landmark_writes
    from .private_dialogue import writes as dialogue_writes
    # Account for every exporter before placing relocatable layouts. Fixed tables
    # keep their verified addresses; only their actual written spans are owned.
    content=content_writes(project) if active(project) else []
    world=world_writes(project) if world_active(project) else []
    groups={'Objects / metatiles / entrances':content,'Overworld routes':world,
            'Map selectors':map_writes(project),'Sprite descriptors':sprite_writes(project),
            'Overworld artwork':landmark_writes(project),'NPC events':dialogue_writes(project)}
    fixed=[(TABLE,bytes(TABLE_SIZE),'layout pointers')]+[w for items in groups.values() for w in items]
    arena=ExpandedArena(fixed)
    writes=[];sizes={};pointers={};pending=[]
    changed={r for k,r,_ in project.edits if k=='layout'}
    for resource in list(range(44))+sorted(project.layout_copies):
        data=compressed(project.resource('layout',resource));sizes[resource]=len(data)
        if len(data)>0x8000:raise FormatError('Compressed layout cannot fit within one ROM bank')
        if resource<44 and len(data)<=rom.layouts[resource].end-rom.layouts[resource].start:
            pointers[resource]=rom.layouts[resource].start
            if resource in changed:writes.append((pointers[resource],data,f'layout {resource:02X}'))
        else:pending.append((resource,data))
    # Largest first avoids stranding a large layout behind smaller allocations.
    for resource,data in sorted(pending,key=lambda item:(-len(item[1]),item[0])):
        offset=arena.allocate(len(data));pointers[resource]=offset
        writes.append((offset,data,f'layout {resource:02X} (expanded)'))
    table=bytearray(TABLE_SIZE)
    for resource,offset in pointers.items():table[3*resource:3*resource+3]=cpu_address(offset).to_bytes(3,'little')
    writes.append((TABLE,bytes(table),'expanded 64-entry layout table'))
    for address in LOADERS:
        writes.append((pc(address)+1,cpu_address(TABLE).to_bytes(3,'little'),'layout table address operand'))
        writes.append((pc(address)+10,cpu_address(TABLE+2).to_bytes(3,'little'),'layout table bank operand'))
    writes.extend(content);writes.extend(world)
    used=EXPANDED_SIZE-BASE_SIZE-arena.free
    breakdown={name:sum(len(data) for at,data,_ in items if at>=BASE_SIZE) for name,items in groups.items()}
    breakdown['Layout pointer table']=TABLE_SIZE
    breakdown['Relocated terrain']=sum(len(data) for _,data in pending)
    plan=LayoutPlan(writes,pointers,sizes,(PoolBudget(tuple(pointers),EXPANDED_SIZE-BASE_SIZE,used,False),),TABLE,used)
    plan.storage={'categories':breakdown,'largest_layout_gap':arena.largest}
    return plan


class ExpandedArena:
    """Deterministic allocator over verified appended ROM only, never base gaps."""
    def __init__(self,writes):
        occupied=[]
        for at,data,label in writes:
            if at<BASE_SIZE:
                if at+len(data)>BASE_SIZE:raise FormatError('Resource crosses into expanded storage')
                continue
            end=at+len(data)
            if end>EXPANDED_SIZE:raise FormatError('Resource exceeds expanded storage')
            if data:occupied.append((at,end,label))
        occupied.sort()
        cursor=BASE_SIZE;gaps=[]
        for start,end,label in occupied:
            if start<cursor:raise FormatError('Overlapping expanded resources: '+label)
            if start>cursor:gaps.append((cursor,start))
            cursor=end
        if cursor<EXPANDED_SIZE:gaps.append((cursor,EXPANDED_SIZE))
        # Every span is bank-contained; remaining fragments remain reusable.
        self.gaps=[]
        for start,end in gaps:
            while start<end:
                boundary=min(end,((start//0x8000)+1)*0x8000)
                self.gaps.append((start,boundary));start=boundary
    @property
    def free(self):return sum(end-start for start,end in self.gaps)
    @property
    def largest(self):return max((end-start for start,end in self.gaps),default=0)
    def allocate(self,size):
        candidates=[(end-start,start,i) for i,(start,end) in enumerate(self.gaps) if end-start>=size]
        if not candidates:raise FormatError(f'Expanded layout storage is full for a {size:,}-byte bank-local layout; {self.free:,} bytes remain in total, largest block {self.largest:,}.')
        _,start,i=min(candidates);end=self.gaps[i][1]
        if start+size==end:self.gaps.pop(i)
        else:self.gaps[i]=(start+size,end)
        return start
