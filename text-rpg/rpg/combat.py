"""Combat resolution using 5e mechanics.

Real-time-friendly adaptation of turn-based 5e combat: when you attack,
one exchange resolves. Initiative is rolled when you first engage a
monster and decides who strikes first in that opening exchange; after
that, the monster swings back after each of your attacks. Multiple
players can gang up on the same monster.
"""

from __future__ import annotations

from . import dice
from .character import Character, fmt_mod
from .world import Monster


def roll_initiative(char: Character, monster: Monster) -> tuple[bool, str]:
    """Roll initiative for an opening exchange. Returns (player_first, text)."""
    p_total, p_nat, _ = dice.d20(char.initiative_mod)
    m_total, m_nat, _ = dice.d20(monster.mtype.initiative_mod)
    player_first = p_total >= m_total  # ties go to the player; be kind
    text = (
        f"Initiative — you {p_total} (d20 {p_nat}{fmt_mod(char.initiative_mod)}) "
        f"vs {monster.name} {m_total}: "
        + ("you act first!" if player_first else f"the {monster.name} acts first!")
    )
    return player_first, text


def player_attack(char: Character, monster: Monster) -> tuple[list[str], int]:
    """Resolve the player's attack. Returns (log lines, damage dealt)."""
    lines = []
    adv = False
    total, natural, desc = dice.d20(char.attack_bonus(), advantage=adv)
    # Halfling luck: reroll natural 1s.
    if natural == 1 and char.race_key == "halfling":
        lines.append("Your halfling luck kicks in — you reroll the natural 1!")
        total, natural, desc = dice.d20(char.attack_bonus())
    weapon = char.cclass.weapon.name
    if natural == 1:
        lines.append(f"You attack the {monster.name} with your {weapon}: {desc} — natural 1, a wild miss!")
        return lines, 0
    crit = natural == 20
    if not crit and total < monster.mtype.ac:
        lines.append(
            f"You attack the {monster.name} with your {weapon}: {desc} = {total} "
            f"vs AC {monster.mtype.ac} — miss."
        )
        return lines, 0
    dmg = char.damage_roll(crit=crit)
    damage = max(1, dmg.total)
    monster.hp -= damage
    hit_word = "CRITICAL HIT" if crit else "hit"
    lines.append(
        f"You attack the {monster.name} with your {weapon}: {desc} = {total} "
        f"vs AC {monster.mtype.ac} — {hit_word}! Damage {dmg}."
    )
    return lines, damage


def monster_attack(monster: Monster, char: Character) -> tuple[list[str], int]:
    """Resolve the monster's counterattack. Returns (log lines, damage dealt)."""
    lines = []
    mt = monster.mtype
    total, natural, desc = dice.d20(mt.attack_bonus)
    if natural == 1:
        lines.append(f"The {mt.name}'s {mt.attack_name} goes wide — natural 1!")
        return lines, 0
    crit = natural == 20
    if not crit and total < char.armor_class:
        lines.append(
            f"The {mt.name} retaliates with a {mt.attack_name}: {desc} = {total} "
            f"vs your AC {char.armor_class} — it misses you."
        )
        return lines, 0
    dmg = dice.parse_and_roll(mt.damage)
    if crit:
        dmg.rolls += dice.parse_and_roll(mt.damage).rolls
    damage = max(1, dmg.total)
    char.hp = max(0, char.hp - damage)
    hit_word = "CRITICAL HIT" if crit else "hits you"
    lines.append(
        f"The {mt.name} retaliates with a {mt.attack_name}: {desc} = {total} "
        f"vs your AC {char.armor_class} — {hit_word} for {damage} damage! "
        f"({char.hp}/{char.max_hp} HP)"
    )
    return lines, damage
