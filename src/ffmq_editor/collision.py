"""Conservative movement variants: never allocate or overwrite tile definitions."""

def describe(value):
    level=value&7
    text='Blocks ordinary walking' if level==7 else 'Accepts any traversal level' if level==0 else f'Traversal level {level} (also accepts level 0)'
    if value&8 and level not in (0,7):text+='; also accepts level 1'
    if value&0xf0:text+='; additional behavior bits present'
    return text

def reserved_remaps(p,area=None):
    lists=range(11) if area is None else {action.value for a in p.rom.areas if p.tileset(a.id)==p.tileset(area) for action in p.rom.area_actions[a.id] if action.opcode==0x23}
    return {tile for i in lists for pair in p.rom.remaps(i) for tile in pair}

def variants(p,area,tile):
    resource=p.tileset(area);graphics=p.fixed('metatile_graphics',resource);attrs=p.fixed('metatile_attributes',resource);props=p.fixed('properties',resource)
    # A tile which participates in a known area replacement list cannot safely be
    # substituted without a state-aware ownership analysis.
    reserved=reserved_remaps(p,area)
    if tile in reserved:return []
    return [i for i in range(128) if i not in reserved and i!=tile and graphics[i*4:i*4+4]==graphics[tile*4:tile*4+4] and attrs[i]==attrs[tile] and props[i*2+1]==props[tile*2+1]]

def replacement(p,area,tile,movement):
    props=p.fixed('properties',p.tileset(area))
    if props[tile*2]==movement:return tile
    if props[tile*2+1]&0xe0==0x80:raise ValueError('Entrance triggers require the entrance editor; collision painting leaves them unchanged.')
    for candidate in variants(p,area,tile):
        if props[candidate*2]==movement:return candidate
    raise ValueError('No existing matching-art variant preserves the other behavior bits. No tile definition was overwritten. Inspect this square for available variants.')

def allocation_audit(p,area):
    # Broad reservation avoids falsely treating a currently absent state as free.
    local_used={0}
    shared=[a for a in p.rom.areas if p.tileset(a.id)==p.tileset(area)]
    for a in shared:local_used.update(c&127 for c in p.resource('layout',p.layout_id(a.id)))
    used={0}
    layouts=set(range(len(p.rom.layouts)))|{p.layout_id(a.id) for a in p.rom.areas}
    for i in layouts:
        used.update(c&127 for c in p.resource('layout',i))
    for change in p.rom.changes:used.update(c&127 for c in p.resource('change',change.id))
    used.update(reserved_remaps(p))
    return {'tileset':p.tileset(area),'absent_from_shared_base_layouts':[i for i in range(128) if i not in local_used],'static_candidates':[i for i in range(128) if i not in used],
        'verified_free':[],
        'blockers':['Native and runtime-generated tile writes have not been exhaustively bounded.',
        'Background-generated cells and indirect event writes can reference tiles absent from stored layouts.',
        'Private metatile sets still contain only 128 entries; expansion does not remove this limit.'],
        'scope':'All stored layouts, project layouts, map-change resources, all 11 metatile replacement lists, and tile zero are reserved. Static candidates are not verified free slots.'}
