# Emberfall (working title)

A text-based multiplayer RPG prototype built on **D&D 5e mechanics** — the
first step toward an eventual MMORPG. For now the whole world is text:
players connect to a shared server, make characters, explore, fight
monsters, and talk to each other with `say`, `shout`, and `tell`.

Zero dependencies — Python 3.10+ standard library only.

## Quick start

Start the server:

```bash
cd text-rpg
python3 server.py            # listens on port 4000
```

Connect (each connection is one player — open several terminals to play
together):

```bash
python3 client.py            # or: nc localhost 4000
```

## What's implemented (5e rules)

- **Character creation**: 6 races, 4 classes (fighter, rogue, wizard,
  cleric), standard array or 4d6-drop-lowest ability scores, racial
  bonuses and a signature trait each.
- **The d20 engine**: ability checks for all 18 SRD skills, saving
  throws with class proficiencies, advantage/disadvantage support,
  freeform dice rolls (`roll 2d6+3`).
- **Combat**: initiative on engagement, attack roll vs. AC, natural
  1s/20s, crits double the damage dice, halfling luck rerolls nat 1s.
  Monsters (giant rats → goblins, wolves, skeletons, orcs → an ogre
  boss) use SRD stat blocks and respawn ~90s after dying.
- **Progression**: 5e XP thresholds through level 10, proficiency bonus
  scaling, HP gains per level, long rests in safe rooms.
- **Multiplayer**: shared world state, room presence, players see each
  other move/fight/emote, private whispers, world shouts, `who` list.
- **Persistence**: characters autosave to `characters.json` and are
  restored by name when you reconnect. Death is merciful for now — you
  wake up in the temple at 1 HP.

## Commands

| Category  | Commands |
|-----------|----------|
| Movement  | `look` (`l`), `go north`, or just `n s e w u d` |
| Talking   | `say <msg>` (or `'msg`), `shout <msg>`, `tell <player> <msg>`, `who` |
| Adventure | `attack <monster>` (`a`), `flee`, `rest` |
| Character | `stats`, `roll 2d6+3`, `check stealth`, `save dex` |
| Misc      | `help`, `quit` |

## The world so far

A starter zone of nine rooms: the safe village of Emberfall (square,
tavern, temple, gate) opening onto fields, a forest, ruins, caves, and
an ogre's lair — roughly ordered by difficulty. Bring friends for the
warrens.

## Architecture notes (with the MMO in mind)

- `rpg/dice.py` — dice notation parsing, d20 with adv/dis, 4d6-drop-low.
- `rpg/character.py` — races/classes/skills data tables, `Character`
  with derived 5e stats, leveling, and JSON persistence.
- `rpg/world.py` — rooms, exits, monster stat blocks, spawns/respawns.
- `rpg/combat.py` — attack/initiative resolution, pure game logic.
- `rpg/game.py` — the engine: sessions, command dispatch, chat,
  broadcast. **Transport-agnostic**: it only talks through per-player
  `send()` callables, so swapping the telnet-style TCP front end for
  websockets (or a real client) later touches only `server.py`.
- `server.py` — asyncio TCP front end + world tick/autosave loop.
- `client.py` — a minimal line-based client (netcat also works).

House rules welcome — mechanics follow 5e "mostly, unless we modify
them," and everything is table-driven to make modifying easy.
