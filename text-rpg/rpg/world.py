"""The game world: rooms, exits, and monster spawns.

A small starter zone — a village hub with a few wilderness areas of
increasing danger. Monsters use 5e SRD stats and respawn a little while
after being slain.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from . import dice

RESPAWN_SECONDS = 90


@dataclass(frozen=True)
class MonsterType:
    key: str
    name: str
    ac: int
    hp_dice: str          # e.g. "2d6" — rolled per spawn
    attack_bonus: int
    damage: str           # e.g. "1d6+2"
    attack_name: str
    xp: int
    initiative_mod: int


# 5e SRD stat blocks (simplified to a single attack each).
MONSTER_TYPES = {
    "rat": MonsterType("rat", "giant rat", 12, "2d6", 4, "1d4+2", "bite", 25, 2),
    "goblin": MonsterType("goblin", "goblin", 15, "2d6", 4, "1d6+2", "scimitar slash", 50, 2),
    "wolf": MonsterType("wolf", "wolf", 13, "2d8+2", 4, "2d4+2", "bite", 50, 2),
    "skeleton": MonsterType("skeleton", "skeleton", 13, "2d8+4", 4, "1d6+2", "shortsword thrust", 50, 2),
    "orc": MonsterType("orc", "orc", 13, "2d8+6", 5, "1d12+3", "greataxe swing", 100, 1),
    "ogre": MonsterType("ogre", "ogre", 11, "7d10+21", 6, "2d8+4", "greatclub smash", 450, -1),
}


class Monster:
    """A live monster instance in a room."""

    _counter = 0

    def __init__(self, mtype: MonsterType):
        Monster._counter += 1
        self.uid = Monster._counter
        self.mtype = mtype
        self.max_hp = max(1, dice.parse_and_roll(mtype.hp_dice).total)
        self.hp = self.max_hp

    @property
    def name(self) -> str:
        return self.mtype.name

    @property
    def alive(self) -> bool:
        return self.hp > 0


@dataclass
class Room:
    room_id: str
    name: str
    description: str
    exits: dict                                   # direction -> room_id
    spawns: list = field(default_factory=list)    # monster type keys
    monsters: list = field(default_factory=list)  # live Monster instances
    _dead_since: dict = field(default_factory=dict)

    def spawn_all(self) -> None:
        for key in self.spawns:
            self.monsters.append(Monster(MONSTER_TYPES[key]))

    def remove_monster(self, monster: Monster) -> None:
        if monster in self.monsters:
            self.monsters.remove(monster)
            self._dead_since[monster.mtype.key] = time.monotonic()

    def respawn_due(self) -> list:
        """Return newly respawned monsters (called periodically by the engine)."""
        now = time.monotonic()
        fresh = []
        for key, died_at in list(self._dead_since.items()):
            if now - died_at >= RESPAWN_SECONDS:
                del self._dead_since[key]
                m = Monster(MONSTER_TYPES[key])
                self.monsters.append(m)
                fresh.append(m)
        return fresh

    def find_monster(self, target: str):
        target = target.lower()
        for m in self.monsters:
            if m.alive and (target in m.name.lower() or target == str(m.uid)):
                return m
        return None


def build_world() -> dict:
    """Construct the starter zone. Returns {room_id: Room}."""
    rooms = [
        Room(
            "square", "Emberfall Village Square",
            "Cobblestones ring a mossy fountain at the heart of Emberfall. "
            "Lanterns sway on iron hooks, and a notice board leans beside "
            "the well. The village is a safe haven — no monsters dare enter.",
            {"north": "gate", "east": "tavern", "west": "temple"},
        ),
        Room(
            "tavern", "The Gilded Griffin Tavern",
            "A low-beamed common room thick with pipe smoke and the smell of "
            "stew. Adventurers swap rumors over battered tankards. A fine "
            "place to meet other travelers — or to rest by the hearth.",
            {"west": "square"},
        ),
        Room(
            "temple", "Temple of the Dawn",
            "Pale morning light filters through high windows onto a quiet "
            "altar. Resting here mends body and spirit alike.",
            {"east": "square"},
        ),
        Room(
            "gate", "North Gate",
            "Emberfall's palisade gate stands open, its timbers scarred by "
            "old claw marks. A rutted road runs north into the fields; the "
            "gate warden eyes departing adventurers with weary sympathy.",
            {"south": "square", "north": "fields"},
        ),
        Room(
            "fields", "Windswept Fields",
            "Waist-high grass ripples away toward a dark treeline. Rats the "
            "size of dogs nose through the furrows of abandoned farmland.",
            {"south": "gate", "north": "forest", "east": "ruins"},
            spawns=["rat", "rat"],
        ),
        Room(
            "forest", "Gloomwood Edge",
            "Crooked pines crowd out the sky. Yellow eyes glint between the "
            "trunks, and something howls, not far off.",
            {"south": "fields", "north": "caves"},
            spawns=["wolf", "goblin"],
        ),
        Room(
            "ruins", "Ruined Watchtower",
            "A collapsed tower juts from the grass like a broken tooth. "
            "Bones litter the rubble — some of them are still moving.",
            {"west": "fields"},
            spawns=["skeleton", "skeleton"],
        ),
        Room(
            "caves", "Blackmaw Caves",
            "The forest gives way to a yawning cave mouth exhaling cold, "
            "sour air. Crude war-drums echo from somewhere deep below.",
            {"south": "forest", "down": "warrens"},
            spawns=["orc", "goblin"],
        ),
        Room(
            "warrens", "The Ogre's Warrens",
            "Gnawed bones and cracked shields carpet this reeking cavern. "
            "Something enormous snores in the dark. This is no place to "
            "wander alone.",
            {"up": "caves"},
            spawns=["ogre"],
        ),
    ]
    world = {r.room_id: r for r in rooms}
    for room in world.values():
        room.spawn_all()
    return world


SAFE_ROOMS = {"square", "tavern", "temple", "gate"}

DIRECTION_ALIASES = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "u": "up", "d": "down",
    "north": "north", "south": "south", "east": "east", "west": "west",
    "up": "up", "down": "down",
}
