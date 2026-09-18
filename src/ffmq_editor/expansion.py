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
    from .expanded_content import active,CONTENT_START,writes as content_writes
    content_active=active(project);landmark_active=project.landmarks is not None and len(project.landmarks)>143;limit=CONTENT_START if content_active or landmark_active else EXPANDED_SIZE
    from .world_expansion import active as world_active, START as WORLD_START, writes as world_writes
    if world_active(project):limit=WORLD_START
    if project.private_dialogues:
        from .private_dialogue import START
        limit=min(limit,START)
    cursor=TABLE+TABLE_SIZE;writes=[];sizes={};pointers={};moved=[]
    changed={r for k,r,_ in project.edits if k=='layout'}
    for resource in list(range(44))+sorted(project.layout_copies):
        data=compressed(project.resource('layout',resource));sizes[resource]=len(data)
        if len(data)>0x8000:raise FormatError('Compressed layout cannot fit within one ROM bank')
        if resource<44 and len(data)<=rom.layouts[resource].end-rom.layouts[resource].start:
            pointers[resource]=rom.layouts[resource].start
            if resource in changed:writes.append((pointers[resource],data,f'layout {resource:02X}'))
        else:
            if cursor//0x8000!=(cursor+len(data)-1)//0x8000:cursor=(cursor//0x8000+1)*0x8000
            if cursor+len(data)>limit:raise FormatError('Expanded layout storage is full')
            pointers[resource]=cursor;writes.append((cursor,data,f'layout {resource:02X} (expanded)'));moved.append(resource);cursor+=len(data)
    table=bytearray(TABLE_SIZE)
    for resource,offset in pointers.items():table[3*resource:3*resource+3]=cpu_address(offset).to_bytes(3,'little')
    writes.append((TABLE,bytes(table),'expanded 64-entry layout table'))
    for address in LOADERS:
        writes.append((pc(address)+1,cpu_address(TABLE).to_bytes(3,'little'),'layout table address operand'))
        writes.append((pc(address)+10,cpu_address(TABLE+2).to_bytes(3,'little'),'layout table bank operand'))
    # Includes the table and any bank-alignment padding, not just payload bytes.
    if content_active:writes.extend(content_writes(project))
    if world_active(project):writes.extend(world_writes(project))
    used=cursor-BASE_SIZE+(EXPANDED_SIZE-limit)
    return LayoutPlan(writes,pointers,sizes,(PoolBudget(tuple(pointers),EXPANDED_SIZE-BASE_SIZE,used,False),),TABLE,used)
