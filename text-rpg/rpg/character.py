"""Characters and 5e rules: races, classes, abilities, leveling.

A trimmed-down implementation of the D&D 5e SRD character rules — enough
to make checks, saves, and combat feel like the tabletop game. House
rules can be layered on later; everything derives from the data tables
at the top of this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import dice

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

ABILITY_NAMES = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}

# 5e standard array, assigned in each class's priority order at creation.
STANDARD_ARRAY = (15, 14, 13, 12, 10, 8)

# Skill -> governing ability (5e SRD).
SKILLS = {
    "acrobatics": "dex",
    "animal handling": "wis",
    "arcana": "int",
    "athletics": "str",
    "deception": "cha",
    "history": "int",
    "insight": "wis",
    "intimidation": "cha",
    "investigation": "int",
    "medicine": "wis",
    "nature": "int",
    "perception": "wis",
    "performance": "cha",
    "persuasion": "cha",
    "religion": "int",
    "sleight of hand": "dex",
    "stealth": "dex",
    "survival": "wis",
}

# XP needed to *reach* each level (index = level), per the 5e table.
XP_THRESHOLDS = [0, 0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000]
MAX_LEVEL = len(XP_THRESHOLDS) - 1


@dataclass(frozen=True)
class Race:
    name: str
    bonuses: dict  # ability -> racial bonus
    speed: int
    trait: str


RACES = {
    "human": Race("Human", {a: 1 for a in ABILITIES}, 30, "+1 to all ability scores"),
    "elf": Race("Elf", {"dex": 2, "int": 1}, 30, "Keen senses: proficiency in Perception"),
    "dwarf": Race("Dwarf", {"con": 2, "wis": 1}, 25, "Dwarven resilience: advantage vs. poison"),
    "halfling": Race("Halfling", {"dex": 2, "cha": 1}, 25, "Lucky: reroll natural 1s on attacks"),
    "half-orc": Race("Half-Orc", {"str": 2, "con": 1}, 30, "Relentless: drop to 1 HP instead of 0 once per rest"),
    "gnome": Race("Gnome", {"int": 2, "con": 1}, 25, "Gnome cunning: advantage on INT/WIS/CHA saves vs. magic"),
}


@dataclass(frozen=True)
class Weapon:
    name: str
    damage: str          # dice notation, e.g. "1d8"
    ability: str         # attack ability ("str" or "dex")
    two_handed: bool = False


@dataclass(frozen=True)
class CharClass:
    name: str
    hit_die: int
    save_profs: tuple            # proficient saving throws
    skill_profs: tuple           # proficient skills
    array_priority: tuple        # order the standard array is assigned
    weapon: Weapon               # starting weapon
    armor_class_base: int        # AC before DEX (armor baked in for simplicity)
    max_dex_to_ac: int           # heavy armor limits DEX bonus


CLASSES = {
    "fighter": CharClass(
        name="Fighter", hit_die=10,
        save_profs=("str", "con"),
        skill_profs=("athletics", "intimidation"),
        array_priority=("str", "con", "dex", "wis", "cha", "int"),
        weapon=Weapon("longsword", "1d8", "str"),
        armor_class_base=16, max_dex_to_ac=2,  # chain mail + shield-ish
    ),
    "rogue": CharClass(
        name="Rogue", hit_die=8,
        save_profs=("dex", "int"),
        skill_profs=("stealth", "acrobatics", "perception", "sleight of hand"),
        array_priority=("dex", "int", "con", "wis", "cha", "str"),
        weapon=Weapon("shortsword", "1d6", "dex"),
        armor_class_base=11, max_dex_to_ac=10,  # leather armor
    ),
    "wizard": CharClass(
        name="Wizard", hit_die=6,
        save_profs=("int", "wis"),
        skill_profs=("arcana", "investigation"),
        array_priority=("int", "con", "dex", "wis", "cha", "str"),
        weapon=Weapon("fire bolt", "1d10", "int"),  # cantrip as the attack
        armor_class_base=10, max_dex_to_ac=10,
    ),
    "cleric": CharClass(
        name="Cleric", hit_die=8,
        save_profs=("wis", "cha"),
        skill_profs=("medicine", "religion"),
        array_priority=("wis", "con", "str", "dex", "cha", "int"),
        weapon=Weapon("mace", "1d6", "str"),
        armor_class_base=14, max_dex_to_ac=2,  # scale mail
    ),
}


def modifier(score: int) -> int:
    return (score - 10) // 2


def fmt_mod(mod: int) -> str:
    return f"+{mod}" if mod >= 0 else str(mod)


@dataclass
class Character:
    name: str
    race_key: str
    class_key: str
    scores: dict                      # ability -> score (racial bonuses included)
    level: int = 1
    xp: int = 0
    hp: int = 0
    max_hp: int = 0
    room_id: str = "square"

    # -- creation ------------------------------------------------------

    @classmethod
    def create(cls, name: str, race_key: str, class_key: str, rolled: bool) -> "Character":
        race = RACES[race_key]
        cclass = CLASSES[class_key]
        if rolled:
            base = sorted((dice.ability_score_roll()[0] for _ in range(6)), reverse=True)
        else:
            base = list(STANDARD_ARRAY)
        scores = {}
        for ability, score in zip(cclass.array_priority, base):
            scores[ability] = score + race.bonuses.get(ability, 0)
        char = cls(name=name, race_key=race_key, class_key=class_key, scores=scores)
        char.max_hp = cclass.hit_die + char.mod("con")  # max hit die at level 1
        char.hp = char.max_hp
        return char

    # -- derived stats -------------------------------------------------

    @property
    def race(self) -> Race:
        return RACES[self.race_key]

    @property
    def cclass(self) -> CharClass:
        return CLASSES[self.class_key]

    @property
    def proficiency(self) -> int:
        return 2 + (self.level - 1) // 4

    @property
    def armor_class(self) -> int:
        c = self.cclass
        return c.armor_class_base + min(self.mod("dex"), c.max_dex_to_ac)

    @property
    def initiative_mod(self) -> int:
        return self.mod("dex")

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def mod(self, ability: str) -> int:
        return modifier(self.scores[ability])

    def attack_bonus(self) -> int:
        return self.mod(self.cclass.weapon.ability) + self.proficiency

    def damage_roll(self, crit: bool = False) -> dice.RollResult:
        result = dice.parse_and_roll(self.cclass.weapon.damage)
        if crit:  # crits double the dice, not the modifier
            result.rolls += dice.parse_and_roll(self.cclass.weapon.damage).rolls
        result.modifier += self.mod(self.cclass.weapon.ability)
        return result

    def skill_bonus(self, skill: str) -> int:
        bonus = self.mod(SKILLS[skill])
        proficient = skill in self.cclass.skill_profs
        if skill == "perception" and self.race_key == "elf":
            proficient = True
        if proficient:
            bonus += self.proficiency
        return bonus

    def save_bonus(self, ability: str) -> int:
        bonus = self.mod(ability)
        if ability in self.cclass.save_profs:
            bonus += self.proficiency
        return bonus

    # -- progression ---------------------------------------------------

    def gain_xp(self, amount: int) -> list[str]:
        """Add XP; returns any level-up messages."""
        self.xp += amount
        messages = []
        while self.level < MAX_LEVEL and self.xp >= XP_THRESHOLDS[self.level + 1]:
            self.level += 1
            # Fixed average hit die roll per level, like most tables use.
            gained = self.cclass.hit_die // 2 + 1 + self.mod("con")
            gained = max(1, gained)
            self.max_hp += gained
            self.hp += gained
            messages.append(
                f"*** You reach level {self.level}! Max HP +{gained} "
                f"(now {self.max_hp}), proficiency {fmt_mod(self.proficiency)}. ***"
            )
        return messages

    def long_rest(self) -> None:
        self.hp = self.max_hp

    # -- display -------------------------------------------------------

    def sheet(self) -> str:
        lines = [
            f"=== {self.name} — level {self.level} {self.race.name} {self.cclass.name} ===",
            f"HP {self.hp}/{self.max_hp}   AC {self.armor_class}   "
            f"Proficiency {fmt_mod(self.proficiency)}   XP {self.xp}"
            + (f"/{XP_THRESHOLDS[self.level + 1]}" if self.level < MAX_LEVEL else " (max)"),
        ]
        stats = "   ".join(
            f"{a.upper()} {self.scores[a]} ({fmt_mod(self.mod(a))})" for a in ABILITIES
        )
        lines.append(stats)
        w = self.cclass.weapon
        lines.append(
            f"Weapon: {w.name} — {fmt_mod(self.attack_bonus())} to hit, "
            f"{w.damage}{fmt_mod(self.mod(w.ability))} damage"
        )
        lines.append(f"Racial trait: {self.race.trait}")
        lines.append(f"Saves: " + ", ".join(
            f"{a.upper()} {fmt_mod(self.save_bonus(a))}" for a in ABILITIES))
        profs = ", ".join(sorted(self.cclass.skill_profs))
        lines.append(f"Skill proficiencies: {profs}")
        return "\n".join(lines)

    # -- persistence ---------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "race": self.race_key,
            "class": self.class_key,
            "scores": self.scores,
            "level": self.level,
            "xp": self.xp,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "room_id": self.room_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        return cls(
            name=data["name"],
            race_key=data["race"],
            class_key=data["class"],
            scores=dict(data["scores"]),
            level=data["level"],
            xp=data["xp"],
            hp=data["hp"],
            max_hp=data["max_hp"],
            room_id=data.get("room_id", "square"),
        )
