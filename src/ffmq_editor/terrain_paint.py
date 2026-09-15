"""Prevent accidental field triggers when painting ordinary scenery."""
import numpy as np
from .rom import pc

def scenery_value(w,old,new):
    if old==new or w.paint_triggers.isChecked():return new
    attrs=w.rom.attributes[w.rom.areas[w.area_id].attributes_id]
    # Use effective preview properties to detect the trigger; verify decorative candidates against configured remaps.
    properties=np.frombuffer(w.project.fixed('properties',attrs.tileset),dtype=np.uint8).reshape(128,2)
    def trigger(index):return int(properties[index,1])&0xE0==0x80
    preview_properties=properties.copy()
    for dest,source in w._state.remaps:preview_properties[dest]=preview_properties[source]
    preview_trigger=lambda index:int(preview_properties[index,1])&0xE0==0x80
    if not preview_trigger(new&127) or preview_trigger(old&127):return new
    graphics=w.project.fixed("metatile_graphics",attrs.tileset)
    bits=w.project.fixed("metatile_attributes",attrs.tileset)
    tile=new&127
    candidates=[i for i in range(128) if int(properties[i,1])==0 and properties[i,0]==properties[tile,0] and bits[i]==bits[tile] and graphics[i*4:i*4+4]==graphics[tile*4:tile*4+4]]
    # A remapped definition cannot be guaranteed decorative in every configuration.
    remapped=set()
    for area in w.rom.areas:
        if w.rom.attributes[area.attributes_id].tileset!=attrs.tileset:continue
        for action in w.rom.area_actions[area.id]:
            if action.opcode==0x23:
                for dest,source in w.rom.remaps(action.value):remapped.add(dest)
    candidates=[i for i in candidates if i not in remapped and tile not in remapped]
    if candidates:return candidates[0]|(new&128)
    raise ValueError('This door tile is a working entrance, with no verified decorative equivalent. To create a trigger, enable Paint entrance triggers in Tiles. To relocate an existing entrance, drag it with Entrances.')
