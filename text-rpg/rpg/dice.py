"""Dice rolling for D&D 5e mechanics.

Supports standard dice notation (``2d6+3``), advantage/disadvantage on
d20 rolls, and the classic 4d6-drop-lowest ability score roll.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

_DICE_RE = re.compile(r"^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


@dataclass
class RollResult:
    """Outcome of a dice roll, keeping individual die results for display."""

    rolls: list[int] = field(default_factory=list)
    modifier: int = 0
    dropped: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.rolls) + self.modifier

    def __str__(self) -> str:
        parts = " + ".join(str(r) for r in self.rolls)
        if self.dropped:
            parts += " (dropped {})".format(", ".join(str(d) for d in self.dropped))
        if self.modifier > 0:
            parts += f" + {self.modifier}"
        elif self.modifier < 0:
            parts += f" - {abs(self.modifier)}"
        return f"[{parts}] = {self.total}"


def roll(count: int, sides: int, modifier: int = 0) -> RollResult:
    if count < 1 or count > 100 or sides < 2 or sides > 1000:
        raise ValueError("Roll must be between 1d2 and 100d1000.")
    return RollResult(
        rolls=[random.randint(1, sides) for _ in range(count)],
        modifier=modifier,
    )


def parse_and_roll(notation: str) -> RollResult:
    """Roll dice given standard notation like ``d20``, ``2d6+3``, ``4d8-1``."""
    m = _DICE_RE.match(notation)
    if not m:
        raise ValueError(f"Can't parse dice notation: {notation!r} (try 2d6+3)")
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    modifier = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    return roll(count, sides, modifier)


def d20(modifier: int = 0, advantage: bool = False, disadvantage: bool = False) -> tuple[int, int, str]:
    """Roll a d20 with optional advantage/disadvantage.

    Returns (total, natural_roll, description). Advantage and disadvantage
    cancel each other out, per 5e rules.
    """
    if advantage and disadvantage:
        advantage = disadvantage = False
    a, b = random.randint(1, 20), random.randint(1, 20)
    if advantage:
        natural = max(a, b)
        desc = f"d20 adv({a},{b})->{natural}"
    elif disadvantage:
        natural = min(a, b)
        desc = f"d20 dis({a},{b})->{natural}"
    else:
        natural = a
        desc = f"d20({natural})"
    if modifier:
        desc += f" {'+' if modifier >= 0 else '-'} {abs(modifier)}"
    return natural + modifier, natural, desc


def ability_score_roll() -> tuple[int, list[int]]:
    """4d6, drop the lowest — the classic way to roll a stat."""
    dice = sorted(random.randint(1, 6) for _ in range(4))
    dropped = dice[0]
    kept = dice[1:]
    return sum(kept), [dropped]
