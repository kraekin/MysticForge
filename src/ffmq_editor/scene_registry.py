"""Named scenes checked against v1.0 event pointers, dialogue and terrain triggers.

Area choices are preview contexts, not claims about runtime actor-slot identities.
World $02/$03/$04/$0A are triggered by terrain actions on the listed layouts;
$08 enters Aquaria via destination-B entries 8 (frozen) and 9 (thawed).
"""
from dataclasses import dataclass
from .events import npc_entry, world_entry, opening_entry

@dataclass(frozen=True)
class Scene:
 title: str
 entry: int
 area: int
 table: str
 index: int
 note: str

SCENES = (
 Scene('Hill of Destiny — opening',0x03F862,12,'opening',0,
       'Opening dialogue, walks and audio. Jumping, sinking terrain and special routines remain protected.'),
 Scene('Kaeli — axe conversation',0x03DA2F,16,'npc',0x15,
       'Kaeli’s house. Use the axe and actor routes tab for the coordinated Kaeli/mother route edit.'),
 Scene('Level Forest — Kaeli and the Minotaur',0x03BCD1,13,'world',2,
       'Minotaur encounter and Kaeli’s poisoning aftermath. Battle, map changes and native choreography remain protected.'),
 Scene('Bone Dungeon — Tristam opens the sealed door',0x03BDDC,19,'world',3,
       'Sealed-door demonstration and explosives conversation. Special effects and door changes remain protected.'),
 Scene('Bone Dungeon — Flamerus Rex and Tristam’s treasure',0x03BEA0,22,'world',4,
       'Boss encounter and Earth Crystal aftermath. Battle, rewards and restoration logic remain protected.'),
 Scene('Aquaria — Phoebe uses Wakewater',0x03C179,24,'world',8,
       'Frozen Aquaria’s Wakewater attempt; this does not fully thaw the town. The entry also branches to thawed Aquaria after Water is restored.'),
 Scene('Ice Pyramid — Ice Golem and the Water Crystal',0x03C272,35,'world',10,
       'Boss encounter, Phoebe’s departure and Water restoration flags. Battle and restoration logic remain protected.'),
)

def available(rom):
 """Do not attach a vanilla scene name to an unrecognized/repointed entry."""
 return tuple(s for s in SCENES if
              (opening_entry(rom) if s.table=='opening' else
               npc_entry(rom,s.index) if s.table=='npc' else
               world_entry(rom,s.index)) == s.entry)
