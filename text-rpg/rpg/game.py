"""The game engine: players, commands, chat, and world state.

Transport-agnostic — the engine speaks through each Player's ``send``
callable, so the asyncio TCP server (or any future transport, e.g.
websockets for the eventual MMO client) just wires connections to
Player objects and feeds lines into ``Game.handle_line``.
"""

from __future__ import annotations

import json
import os
import re
import time

from . import dice
from .character import (
    ABILITIES, CLASSES, RACES, SKILLS, Character, fmt_mod,
)
from . import combat
from .world import DIRECTION_ALIASES, SAFE_ROOMS, build_world

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'-]{1,15}$")

MOTD = r"""
==========================================================
   E M B E R F A L L   —  a text-based multiplayer RPG
        (working title — powered by 5e mechanics)
==========================================================
"""

HELP_TEXT = """\
--- Commands ---------------------------------------------------------
Movement    look (l)             look around the room
            go <dir> / n s e w u d   move between areas
Talking     say <msg>  (')       speak to everyone in the room
            shout <msg>          shout to the whole world
            tell <player> <msg>  whisper privately to a player
            who                  list everyone online
Adventure   attack <monster> (a) fight! rolls initiative, then attacks
            flee                 disengage and run back the way you came
            rest                 long rest (safe rooms only): full HP
Character   stats                your full character sheet
            roll <dice>          roll dice, e.g. roll 2d6+3
            check <skill>        ability check, e.g. check stealth
            save <ability>       saving throw, e.g. save dex
Misc        help                 this text
            quit                 save and disconnect
----------------------------------------------------------------------"""


class Player:
    """A connected session. ``send`` is provided by the transport layer."""

    def __init__(self, send):
        self.send = send            # callable(str) -> None, appends newline
        self.character = None       # set once creation/login completes
        self.stage = "name"         # character-creation state machine
        self.pending = {}           # scratch space during creation
        self.engaged = None         # Monster we've rolled initiative against

    @property
    def name(self):
        return self.character.name if self.character else None


class Game:
    def __init__(self, save_path: str = "characters.json"):
        self.world = build_world()
        self.players: list[Player] = []
        self.save_path = save_path
        self.saved_chars = self._load_saves()

    # ---------------- persistence ----------------

    def _load_saves(self) -> dict:
        if os.path.exists(self.save_path):
            try:
                with open(self.save_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def save_all(self) -> None:
        for p in self.players:
            if p.character:
                self.saved_chars[p.character.name.lower()] = p.character.to_dict()
        tmp = self.save_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.saved_chars, f, indent=2)
        os.replace(tmp, self.save_path)

    # ---------------- connection lifecycle ----------------

    def connect(self, send) -> Player:
        player = Player(send)
        self.players.append(player)
        player.send(MOTD)
        player.send("What is your name, adventurer?")
        return player

    def disconnect(self, player: Player) -> None:
        if player in self.players:
            self.players.remove(player)
        if player.character:
            self.saved_chars[player.character.name.lower()] = player.character.to_dict()
            self.save_all()
            self.broadcast_room(
                player.character.room_id,
                f"{player.character.name} fades from the world.",
                exclude=player,
            )

    # ---------------- messaging helpers ----------------

    def broadcast(self, message: str, exclude=None) -> None:
        for p in self.players:
            if p.character and p is not exclude:
                p.send(message)

    def broadcast_room(self, room_id: str, message: str, exclude=None) -> None:
        for p in self.players:
            if p.character and p.character.room_id == room_id and p is not exclude:
                p.send(message)

    def find_player(self, name: str):
        name = name.lower()
        for p in self.players:
            if p.character and p.character.name.lower() == name:
                return p
        return None

    # ---------------- world upkeep (called by server timer) ----------------

    def tick(self) -> None:
        for room in self.world.values():
            for m in room.respawn_due():
                self.broadcast_room(room.room_id, f"A {m.name} prowls into the area!")

    # ---------------- input dispatch ----------------

    def handle_line(self, player: Player, line: str) -> None:
        line = line.strip()
        if player.character is None:
            self._handle_creation(player, line)
            return
        if not line:
            return
        self._handle_command(player, line)

    # ---------------- character creation flow ----------------

    def _handle_creation(self, player: Player, line: str) -> None:
        if player.stage == "name":
            if not NAME_RE.match(line):
                player.send("Names are 2-16 letters (apostrophes and dashes ok). Try again:")
                return
            name = line.capitalize()
            if self.find_player(name):
                player.send("Someone by that name is already adventuring. Pick another:")
                return
            saved = self.saved_chars.get(name.lower())
            if saved:
                player.character = Character.from_dict(saved)
                if player.character.hp <= 0:
                    player.character.hp = 1  # you were dragged back to safety
                    player.character.room_id = "temple"
                self._enter_world(player, returning=True)
                return
            player.pending["name"] = name
            races = ", ".join(RACES)
            player.send(f"Welcome, {name}! Choose your race: {races}")
            player.stage = "race"
        elif player.stage == "race":
            key = line.lower()
            if key not in RACES:
                player.send("Choose one of: " + ", ".join(RACES))
                return
            player.pending["race"] = key
            player.send(f"A {RACES[key].name} — {RACES[key].trait}.")
            player.send("Choose your class: " + ", ".join(CLASSES))
            player.stage = "class"
        elif player.stage == "class":
            key = line.lower()
            if key not in CLASSES:
                player.send("Choose one of: " + ", ".join(CLASSES))
                return
            player.pending["class"] = key
            player.send(
                "Ability scores: type 'standard' for the standard array "
                "(15 14 13 12 10 8) or 'roll' for 4d6-drop-lowest. Fate is fickle."
            )
            player.stage = "scores"
        elif player.stage == "scores":
            choice = line.lower()
            if choice not in ("standard", "roll"):
                player.send("Type 'standard' or 'roll'.")
                return
            player.character = Character.create(
                player.pending["name"],
                player.pending["race"],
                player.pending["class"],
                rolled=(choice == "roll"),
            )
            self._enter_world(player, returning=False)

    def _enter_world(self, player: Player, returning: bool) -> None:
        char = player.character
        player.stage = "playing"
        player.send("")
        player.send(char.sheet())
        player.send("")
        player.send("Type 'help' for commands. Talk with say/shout/tell — every voice is text.")
        player.send("")
        verb = "returns to" if returning else "steps into"
        self.broadcast(f"*** {char.name} the {char.cclass.name} {verb} the world. ***", exclude=player)
        self._look(player)
        self.save_all()

    # ---------------- command handling ----------------

    def _handle_command(self, player: Player, line: str) -> None:
        # Shortcuts: 'a bit of punctuation goes a long way in a MUD.
        if line.startswith("'"):
            line = "say " + line[1:]
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in DIRECTION_ALIASES:
            self._move(player, DIRECTION_ALIASES[cmd])
        elif cmd == "go" and arg:
            direction = DIRECTION_ALIASES.get(arg.lower())
            if direction:
                self._move(player, direction)
            else:
                player.send("Go where? (north, south, east, west, up, down)")
        elif cmd in ("look", "l"):
            self._look(player)
        elif cmd == "say":
            self._say(player, arg)
        elif cmd == "shout":
            self._shout(player, arg)
        elif cmd == "tell":
            self._tell(player, arg)
        elif cmd == "who":
            self._who(player)
        elif cmd in ("attack", "a", "kill"):
            self._attack(player, arg)
        elif cmd == "flee":
            self._flee(player)
        elif cmd == "rest":
            self._rest(player)
        elif cmd in ("stats", "sheet", "score"):
            player.send(player.character.sheet())
        elif cmd == "roll":
            self._roll(player, arg)
        elif cmd == "check":
            self._check(player, arg)
        elif cmd == "save":
            self._saving_throw(player, arg)
        elif cmd in ("help", "?"):
            player.send(HELP_TEXT)
        elif cmd in ("quit", "exit"):
            player.send("Your deeds are recorded. Farewell!")
            raise Disconnect()
        else:
            player.send(f"Unknown command: {cmd!r}. Type 'help' for the list.")

    # ---------------- world commands ----------------

    def _room(self, player: Player):
        return self.world[player.character.room_id]

    def _look(self, player: Player) -> None:
        room = self._room(player)
        player.send(f"\n[{room.name}]")
        player.send(room.description)
        exits = ", ".join(room.exits)
        player.send(f"Exits: {exits}")
        others = [
            p.character.name for p in self.players
            if p.character and p is not player
            and p.character.room_id == room.room_id
        ]
        if others:
            player.send("Adventurers here: " + ", ".join(others))
        alive = [m for m in room.monsters if m.alive]
        for m in alive:
            hurt = "" if m.hp == m.max_hp else " (wounded)"
            player.send(f"A {m.name} is here{hurt}.")

    def _move(self, player: Player, direction: str) -> None:
        room = self._room(player)
        dest_id = room.exits.get(direction)
        if not dest_id:
            player.send(f"You can't go {direction} from here.")
            return
        char = player.character
        player.engaged = None
        self.broadcast_room(room.room_id, f"{char.name} leaves {direction}.", exclude=player)
        char.room_id = dest_id
        self.broadcast_room(dest_id, f"{char.name} arrives.", exclude=player)
        self._look(player)

    # ---------------- communication (text is the whole world, for now) ----

    def _say(self, player: Player, message: str) -> None:
        if not message:
            player.send("Say what?")
            return
        char = player.character
        player.send(f'You say, "{message}"')
        self.broadcast_room(char.room_id, f'{char.name} says, "{message}"', exclude=player)

    def _shout(self, player: Player, message: str) -> None:
        if not message:
            player.send("Shout what?")
            return
        char = player.character
        player.send(f'You shout, "{message}"')
        self.broadcast(f'{char.name} shouts, "{message}"', exclude=player)

    def _tell(self, player: Player, arg: str) -> None:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            player.send("Usage: tell <player> <message>")
            return
        target = self.find_player(parts[0])
        if not target:
            player.send(f"No one named {parts[0]!r} is online.")
            return
        if target is player:
            player.send("You mutter to yourself.")
            return
        player.send(f'You tell {target.character.name}, "{parts[1]}"')
        target.send(f'{player.character.name} tells you, "{parts[1]}"')

    def _who(self, player: Player) -> None:
        player.send("--- Adventurers online ---")
        for p in self.players:
            if p.character:
                c = p.character
                marker = " (you)" if p is player else ""
                player.send(
                    f"  {c.name} — level {c.level} {c.race.name} {c.cclass.name}, "
                    f"in {self.world[c.room_id].name}{marker}"
                )

    # ---------------- adventure commands ----------------

    def _attack(self, player: Player, target: str) -> None:
        char = player.character
        room = self._room(player)
        if room.room_id in SAFE_ROOMS:
            player.send("The village wards prevent violence here.")
            return
        if not target:
            alive = [m for m in room.monsters if m.alive]
            if not alive:
                player.send("There is nothing here to fight.")
                return
            monster = alive[0]
        else:
            monster = room.find_monster(target)
            if not monster:
                player.send(f"You don't see {target!r} here.")
                return

        monster_strikes_first = False
        if player.engaged is not monster:
            player.engaged = monster
            player_first, text = combat.roll_initiative(char, monster)
            player.send(text)
            monster_strikes_first = not player_first
            self.broadcast_room(
                room.room_id,
                f"{char.name} squares off against the {monster.name}!",
                exclude=player,
            )

        if monster_strikes_first:
            self._monster_turn(player, monster, room)
            if not char.alive:
                return

        lines, _ = combat.player_attack(char, monster)
        for ln in lines:
            player.send(ln)
        self.broadcast_room(
            room.room_id,
            f"{char.name} attacks the {monster.name}!",
            exclude=player,
        )

        if not monster.alive:
            self._monster_slain(player, monster, room)
            return

        self._monster_turn(player, monster, room)

    def _monster_turn(self, player: Player, monster, room) -> None:
        char = player.character
        lines, _ = combat.monster_attack(monster, char)
        for ln in lines:
            player.send(ln)
        if not char.alive:
            player.engaged = None
            player.send(
                "\nYou fall! Darkness takes you... but this is a merciful "
                "prototype: villagers drag you to the Temple of the Dawn."
            )
            self.broadcast_room(
                room.room_id, f"{char.name} falls to the {monster.name}!", exclude=player,
            )
            char.hp = 1
            char.room_id = "temple"
            self.broadcast_room(
                "temple",
                f"Villagers carry {char.name}'s battered body into the temple.",
                exclude=player,
            )
            self._look(player)
            self.save_all()

    def _monster_slain(self, player: Player, monster, room) -> None:
        char = player.character
        player.engaged = None
        room.remove_monster(monster)
        player.send(f"The {monster.name} is slain! You gain {monster.mtype.xp} XP.")
        self.broadcast_room(
            room.room_id,
            f"{char.name} slays the {monster.name}!",
            exclude=player,
        )
        for msg in char.gain_xp(monster.mtype.xp):
            player.send(msg)
            self.broadcast(
                f"*** {char.name} has reached level {char.level}! ***", exclude=player,
            )
        # Anyone else engaged with this monster is released.
        for p in self.players:
            if p.engaged is monster:
                p.engaged = None
        self.save_all()

    def _flee(self, player: Player) -> None:
        room = self._room(player)
        threats = [m for m in room.monsters if m.alive]
        if not threats and player.engaged is None:
            player.send("Nothing here is worth fleeing from.")
            return
        player.engaged = None
        back = next(iter(room.exits))
        player.send("You turn and run!")
        self._move(player, back)

    def _rest(self, player: Player) -> None:
        char = player.character
        if player.character.room_id not in SAFE_ROOMS:
            player.send("Too dangerous to rest here — return to the village.")
            return
        char.long_rest()
        player.send(f"You take a long rest. HP restored to {char.hp}/{char.max_hp}.")
        self.broadcast_room(
            char.room_id, f"{char.name} settles down to rest.", exclude=player,
        )
        self.save_all()

    # ---------------- dice commands ----------------

    def _roll(self, player: Player, notation: str) -> None:
        if not notation:
            player.send("Usage: roll <dice>, e.g. roll d20 or roll 2d6+3")
            return
        try:
            result = dice.parse_and_roll(notation)
        except ValueError as e:
            player.send(str(e))
            return
        char = player.character
        player.send(f"You roll {notation}: {result}")
        self.broadcast_room(
            char.room_id, f"{char.name} rolls {notation}: {result}", exclude=player,
        )

    def _check(self, player: Player, skill: str) -> None:
        skill = skill.lower().strip()
        if skill not in SKILLS:
            player.send("Skills: " + ", ".join(sorted(SKILLS)))
            return
        char = player.character
        bonus = char.skill_bonus(skill)
        total, natural, desc = dice.d20(bonus)
        prof = " (proficient)" if bonus != char.mod(SKILLS[skill]) else ""
        player.send(f"{skill.title()} check{prof}: {desc} = {total}")
        self.broadcast_room(
            char.room_id,
            f"{char.name} makes a {skill.title()} check: {total}",
            exclude=player,
        )

    def _saving_throw(self, player: Player, ability: str) -> None:
        ability = ability.lower().strip()
        if ability not in ABILITIES:
            player.send("Saves: " + ", ".join(a.upper() for a in ABILITIES))
            return
        char = player.character
        bonus = char.save_bonus(ability)
        total, natural, desc = dice.d20(bonus)
        prof = " (proficient)" if ability in char.cclass.save_profs else ""
        player.send(f"{ability.upper()} saving throw{prof}: {desc} = {total}")
        self.broadcast_room(
            char.room_id,
            f"{char.name} makes a {ability.upper()} save: {total}",
            exclude=player,
        )


class Disconnect(Exception):
    """Raised by the quit command; the transport layer closes the connection."""
