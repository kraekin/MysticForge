"""Bank-local repacking inside the two existing, fully owned layout pools."""
from dataclasses import dataclass
from functools import lru_cache
from .rom import pc,encode_map,FormatError

POOLS=((0x40000,0x47dbe,tuple(range(32))),
       (0x3921e,0x3af3b,tuple(range(32,44))))
POINTERS=pc(0x0b8735)

@lru_cache(maxsize=128)
def compressed(cells):return encode_map(cells)

def cpu_address(offset):return (offset//0x8000)<<16 | 0x8000 | (offset%0x8000)

def verify_pools(rom):
    # Both loaders read the full pointer (address AND bank) from the same table.
    expected=bytes.fromhex('bf35870b8d0009e220bf37870b8d02092269860b')
    for address in (0x0b852b,0x0b861a):
        if rom.data[pc(address):pc(address)+len(expected)]!=expected:
            raise FormatError('Layout relocation loader verification failed')
    if len(rom.layouts)!=44:raise FormatError('Unexpected layout inventory')
    for start,end,ids in POOLS:
        cursor=start
        if start//0x8000!=(end-1)//0x8000:raise FormatError('Layout pool crosses a ROM bank')
        for i in ids:
            original=rom.layouts[i]
            pointer=int.from_bytes(rom.data[POINTERS+3*i:POINTERS+3*i+3],'little')
            if original.start!=cursor or pc(pointer)!=cursor or original.end> end:
                raise FormatError('Layout pool ownership verification failed')
            cursor=original.end
        if cursor!=end:raise FormatError('Layout pool contains unverified space')

@dataclass(frozen=True)
class PoolBudget:
    ids:tuple
    capacity:int
    used:int
    repack:bool

    @property
    def free(self):return self.capacity-self.used

@dataclass
class LayoutPlan:
    writes:list
    pointers:dict
    sizes:dict
    pools:tuple
    table:int=POINTERS
    allocated:int=0
    storage:dict|None=None

def plan_layouts(project,strict=True):
    rom=project.rom;verify_pools(rom)
    project.validate_expansion()
    if project.expanded:
        from .expansion import plan_expanded
        return plan_expanded(project)
    changed={resource for kind,resource,_ in project.edits if kind=='layout'}
    sizes={};payloads={};budgets=[];writes=[];pointers={i:m.start for i,m in enumerate(rom.layouts)}
    for start,end,ids in POOLS:
        for i in ids:
            payloads[i]=compressed(project.resource('layout',i) if i in changed else rom.layouts[i].cells)
            sizes[i]=len(payloads[i])
        repack=any(i in changed and sizes[i]>rom.layouts[i].end-rom.layouts[i].start for i in ids)
        budget=PoolBudget(ids,end-start,sum(sizes[i] for i in ids),repack);budgets.append(budget)
        if budget.free<0:
            if strict:raise FormatError(f'Map storage pool ${ids[0]:02X}–${ids[-1]:02X} needs {budget.used:,} compressed bytes; capacity is {budget.capacity:,} ({-budget.free:,} bytes over). Repacking is already included. Save your project; simplify some layouts in this pool. ROM expansion is not enabled.')
            continue
        cursor=start
        for i in ids:
            if repack:
                pointers[i]=cursor;writes.append((cursor,payloads[i],f'layout {i:02X} (repacked)'));cursor+=sizes[i]
            elif i in changed:writes.append((rom.layouts[i].start,payloads[i],f'layout {i:02X}'))
        if repack:
            for i in ids:
                writes.append((POINTERS+3*i,cpu_address(pointers[i]).to_bytes(3,'little'),f'layout pointer {i:02X}'))
    return LayoutPlan(writes,pointers,sizes,tuple(budgets))
