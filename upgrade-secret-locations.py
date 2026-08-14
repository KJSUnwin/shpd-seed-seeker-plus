#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: upgrade-secret-locations.py PATH_TO_UPSTREAM_APP")

root = Path(sys.argv[1]).resolve()
MARKER = "SHPD-SECRET-LOCATOR-V2"

def read(rel):
    return (root / rel).read_text(encoding="utf-8")

def write(rel, text):
    (root / rel).write_text(text, encoding="utf-8")

def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(
            f"Could not find {label}. Make sure apply-customisation.py runs before this upgrade."
        )
    return text.replace(old, new, 1)

# 1. Rust core
rel = "crates/seedfinder-core/src/main_world.rs"
s = read(rel)

if MARKER not in s:
    anchor = "use crate::generator::{ARTIFACT_ITEMS, ArtifactKind};\n"
    addition = (
        anchor
        + "use crate::geometry::{Point, terrain};\n"
        + "use crate::level::{Level, TrapKind};\n"
    )
    s = replace_once(s, anchor, addition, "locator imports")

    old_struct = '''#[derive(Clone, Debug, PartialEq)]
pub struct ScoutFloorMetadata {
    pub depth: u8,
    pub secret_rooms: Vec<SecretRoomKind>,
    pub artifacts: Vec<ArtifactKind>,
}
'''
    new_struct = '''/// SHPD-SECRET-LOCATOR-V2
#[derive(Clone, Debug, PartialEq)]
pub struct ScoutSecretRoomMetadata {
    pub kind: SecretRoomKind,
    pub adjoining_room: String,
    pub visible_doors: usize,
    pub contains_water: bool,
    pub contains_pit: bool,
    pub wall: &'static str,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ScoutFloorMetadata {
    pub depth: u8,
    pub secret_rooms: Vec<ScoutSecretRoomMetadata>,
    pub artifacts: Vec<ArtifactKind>,
}
'''
    s = replace_once(s, old_struct, new_struct, "ScoutFloorMetadata")

    old_fn = '''fn scout_secret_rooms(rooms: &[Room]) -> Vec<SecretRoomKind> {
    rooms.iter()
        .filter_map(|room| match room.kind {
            RoomKind::Secret(kind) => Some(kind),
            _ => None,
        })
        .collect()
}
'''
    new_fn = r'''fn scout_room_label(kind: RoomKind) -> String {
    match kind {
        RoomKind::Entrance(_) => "Entrance".to_owned(),
        RoomKind::Exit(_) => "Exit/Stairs".to_owned(),
        RoomKind::Standard(kind) => format!("{kind:?}"),
        RoomKind::Connection(kind) => format!("{kind:?}"),
        RoomKind::Special(kind) => format!("{kind:?}"),
        RoomKind::Quest(kind) => format!("{kind:?}"),
        RoomKind::Secret(kind) => format!("Secret {kind:?}"),
    }
}

fn scout_cell_point(cell: usize, width: i32) -> Point {
    let width = usize::try_from(width).expect("positive painted level width");
    Point::new(
        i32::try_from(cell % width).expect("map x fits i32"),
        i32::try_from(cell / width).expect("map y fits i32"),
    )
}

fn scout_room_features(room: &Room, level: &Level) -> (bool, bool) {
    let mut water = false;
    let mut pit = false;

    for y in room.bounds.top.saturating_add(1)..room.bounds.bottom {
        for x in room.bounds.left.saturating_add(1)..room.bounds.right {
            if !level.map.in_bounds(x, y) {
                continue;
            }
            let cell = level.map.cell(x, y);
            let flags = terrain::flags(level.map.cells[cell]);
            water |= flags & terrain::LIQUID != 0;
            pit |= flags & terrain::PIT != 0;
        }
    }

    if !pit {
        pit = level.traps.iter().any(|trap| {
            trap.spec.kind == TrapKind::Pitfall
                && room.inside(scout_cell_point(trap.cell, level.width()))
        });
    }

    (water, pit)
}

fn scout_secret_wall(room: &Room, door: Point) -> &'static str {
    if door.y == room.bounds.top {
        "N"
    } else if door.y == room.bounds.bottom {
        "S"
    } else if door.x == room.bounds.left {
        "W"
    } else if door.x == room.bounds.right {
        "E"
    } else {
        "?"
    }
}

fn scout_secret_rooms(rooms: &[Room], level: &Level) -> Vec<ScoutSecretRoomMetadata> {
    let mut output = Vec::new();

    for (secret_id, secret_room) in rooms.iter().enumerate() {
        let RoomKind::Secret(kind) = secret_room.kind else {
            continue;
        };

        let Some(connection) = secret_room
            .connected
            .iter()
            .find(|connection| !rooms[connection.room].is_secret())
        else {
            continue;
        };

        let adjoining = &rooms[connection.room];

        let door = connection.door.or_else(|| {
            adjoining
                .connected
                .iter()
                .find(|reverse| reverse.room == secret_id)
                .and_then(|reverse| reverse.door)
        });

        let visible_doors = adjoining
            .connected
            .iter()
            .filter(|candidate| !rooms[candidate.room].is_secret())
            .count();

        let (contains_water, contains_pit) = scout_room_features(adjoining, level);

        output.push(ScoutSecretRoomMetadata {
            kind,
            adjoining_room: scout_room_label(adjoining.kind),
            visible_doors,
            contains_water,
            contains_pit,
            wall: door.map_or("?", |door| scout_secret_wall(adjoining, door.point)),
        });
    }

    output
}
'''
    s = replace_once(s, old_fn, new_fn, "scout_secret_rooms")
    s = s.replace(
        "scout_secret_rooms(&floor.painted.rooms)",
        "scout_secret_rooms(&floor.painted.rooms, &floor.painted.level)",
    )
    write(rel, s)

# 2. WASM
rel = "crates/seedfinder-wasm/src/lib.rs"
s = read(rel)

if MARKER not in s:
    old_floor = '''#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ScoutFloorOutput {
    depth: u8,
    secret_rooms: Vec<&'static str>,
    artifacts: Vec<&'static str>,
}
'''
    new_floor = '''/// SHPD-SECRET-LOCATOR-V2
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ScoutSecretRoomOutput {
    kind: &'static str,
    room: String,
    doors: usize,
    water: bool,
    pit: bool,
    wall: &'static str,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ScoutFloorOutput {
    depth: u8,
    secret_rooms: Vec<ScoutSecretRoomOutput>,
    artifacts: Vec<&'static str>,
}
'''
    s = replace_once(s, old_floor, new_floor, "ScoutFloorOutput")

    old_mapping = '''            secret_rooms: floor.secret_rooms.into_iter().map(scout_secret_room_name).collect(),
            artifacts: floor.artifacts.into_iter().map(scout_artifact_name).collect(),
'''
    new_mapping = '''            secret_rooms: floor
                .secret_rooms
                .into_iter()
                .map(|secret| ScoutSecretRoomOutput {
                    kind: scout_secret_room_name(secret.kind),
                    room: secret.adjoining_room,
                    doors: secret.visible_doors,
                    water: secret.contains_water,
                    pit: secret.contains_pit,
                    wall: secret.wall,
                })
                .collect(),
            artifacts: floor.artifacts.into_iter().map(scout_artifact_name).collect(),
'''
    s = replace_once(s, old_mapping, new_mapping, "secret-room WASM mapping")
    write(rel, s)

# 3. Typescript
rel = "web/src/lib/wasm/types.ts"
s = read(rel)

if MARKER not in s:
    old = '''export interface ScoutFloor {
  depth: number
  secretRooms: SecretRoomName[]
  artifacts: ArtifactName[]
}
'''
    new = '''// SHPD-SECRET-LOCATOR-V2
export interface ScoutSecretRoom {
  kind: SecretRoomName
  room: string
  doors: number
  water: boolean
  pit: boolean
  wall: 'N' | 'S' | 'E' | 'W' | '?'
}

export interface ScoutFloor {
  depth: number
  secretRooms: ScoutSecretRoom[]
  artifacts: ArtifactName[]
}
'''
    s = replace_once(s, old, new, "ScoutFloor TypeScript type")
    write(rel, s)

# 4. UI
rel = "web/src/designs/one/ScoutPanel.tsx"
s = read(rel)

if MARKER not in s:
    s = replace_once(
        s,
        '''  ScoutResult,
  SecretRoomName,
''',
        '''  ScoutResult,
  ScoutSecretRoom,
  SecretRoomName,
''',
        "ScoutSecretRoom import",
    )

    old_helpers = '''const prettyScoutToken = (value: string) =>
  value.split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
const secretRoomLabel = (value: SecretRoomName) => prettyScoutToken(value)
const artifactLabel = (value: ArtifactName) => prettyScoutToken(value)
'''
    new_helpers = r'''// SHPD-SECRET-LOCATOR-V2
const prettyScoutToken = (value: string) =>
  value
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')

const secretRoomLabel = (value: SecretRoomName) => prettyScoutToken(value)
const artifactLabel = (value: ArtifactName) => prettyScoutToken(value)

// SHPD-ARTIFACT-SPRITES-V2.2
// Official v3.3.8 ItemSpriteSheet indices.
// Multi-stage artifacts use their base/unupgraded sprite.
const artifactSpriteIndex: Record<ArtifactName, number> = {
  cloak_of_shadows: 240,
  master_thieves_armband: 241,
  talisman_of_foresight: 243,
  timekeepers_hourglass: 244,
  alchemists_toolkit: 245,
  unstable_spellbook: 246,
  ethereal_chains: 248,
  horn_of_plenty: 249,
  chalice_of_blood: 253,
  sandals_of_nature: 256,
  dried_rose: 260,
  holy_tome: 263,
  skeleton_key: 264,
}

const secretRoomSummary = (secret: ScoutSecretRoom) => {
  const parts = [
    secretRoomLabel(secret.kind),
    prettyScoutToken(secret.room),
    `${secret.doors} ${secret.doors === 1 ? 'door' : 'doors'}`,
    secret.water ? 'water' : null,
    secret.pit ? 'pit' : null,
    secret.wall,
  ]
  return parts.filter((part): part is string => Boolean(part)).join(' · ')
}
'''
    s = replace_once(s, old_helpers, new_helpers, "Scout UI helpers")

    old_display = '''                      <div className="d1-plus-floor-meta-row">
                        <span className="d1-plus-floor-meta-label">Secret rooms</span>
                        <b>{secretCount > 0 ? `Yes (${secretCount})` : 'No (0)'}</b>
                        {secretCount > 0 && (
                          <span>{metadata.secretRooms.map(secretRoomLabel).join(', ')}</span>
                        )}
                      </div>
'''
    new_display = '''                      <div className="d1-plus-floor-meta-row">
                        <span className="d1-plus-floor-meta-label">Secret rooms</span>
                        <b>{secretCount > 0 ? `Yes (${secretCount})` : 'No (0)'}</b>
                      </div>
                      {metadata.secretRooms.map((secret, index) => (
                        <div
                          className="d1-plus-secret-line"
                          key={`${secret.kind}-${secret.room}-${secret.wall}-${index}`}
                        >
                          {secretRoomSummary(secret)}
                        </div>
                      ))}
'''
    s = replace_once(s, old_display, new_display, "Scout secret display")

    old_artifact_display = '''                      <div className="d1-plus-floor-meta-row">
                        <span className="d1-plus-floor-meta-label">Artifacts</span>
                        <b>{metadata.artifacts.length > 0 ? metadata.artifacts.length : 'None'}</b>
                        {metadata.artifacts.length > 0 && (
                          <span>{metadata.artifacts.map(artifactLabel).join(', ')}</span>
                        )}
                      </div>
'''
    new_artifact_display = '''                      <div className="d1-plus-floor-meta-row d1-plus-artifact-row">
                        <span className="d1-plus-floor-meta-label">Artifacts</span>
                        {metadata.artifacts.length === 0 ? (
                          <b>None</b>
                        ) : (
                          <div className="d1-plus-artifacts">
                            {metadata.artifacts.map((artifact) => (
                              <span className="d1-plus-artifact" key={artifact}>
                                <Sprite
                                  index={artifactSpriteIndex[artifact]}
                                  size={28}
                                  label={artifactLabel(artifact)}
                                />
                                <span>{artifactLabel(artifact)}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
'''
    s = replace_once(
        s,
        old_artifact_display,
        new_artifact_display,
        "Scout artifact sprite display",
    )
    write(rel, s)

# 5. CSS
rel = "web/src/designs/one/styles.css"
s = read(rel)

if MARKER not in s:
    s += r'''

/* SHPD-SECRET-LOCATOR-V2 */
.d1-plus-secret-line {
  padding-left: 92px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
}

@media (max-width: 520px) {
  .d1-plus-secret-line {
    padding-left: 0;
  }
}

/* SHPD-ARTIFACT-SPRITES-V2.2 */
.d1-plus-artifact-row {
  align-items: center;
}

.d1-plus-artifacts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.d1-plus-artifact {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
}

.d1-plus-artifact > span:last-child {
  opacity: 0.9;
}
'''
    write(rel, s)


# 6. FIX GITHUB PAGES SPRITE PATHS
# The upstream web app assumes it is hosted at domain root:
#   /third_party/shattered-pixel-dungeon/items.png
# Our site is hosted under /shpd-seed-seeker-plus/, so those absolute URLs 404.
# Vite exposes the configured base path through import.meta.env.BASE_URL.
rel = "web/src/lib/sprites.ts"
s = read(rel)

s = replace_once(
    s,
    "const SHEET_URL = '/third_party/shattered-pixel-dungeon/items.png'\n",
    "const SHEET_URL = `${import.meta.env.BASE_URL}third_party/shattered-pixel-dungeon/items.png`\n",
    "item sprite sheet URL",
)

s = replace_once(
    s,
    "const ICON_SHEET_URL = '/third_party/shattered-pixel-dungeon/item_icons.png'\n",
    "const ICON_SHEET_URL = `${import.meta.env.BASE_URL}third_party/shattered-pixel-dungeon/item_icons.png`\n",
    "ring icon sprite sheet URL",
)

write(rel, s)

print("Secret Room Locator V2.3 + artwork + GitHub Pages sprite paths applied successfully.")
