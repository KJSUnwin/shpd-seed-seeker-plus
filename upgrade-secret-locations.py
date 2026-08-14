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


# ===========================================================================
# 7. SEARCHABLE SECRET ROOMS + ARTIFACTS — V2.4
# ===========================================================================

# Browser types
rel = "web/src/lib/wasm/types.ts"
s = read(rel)

s = replace_once(
    s,
    "export interface QueryState {\n  requirements: RequirementState[]\n  maxDepth: number\n",
    "export interface QueryState {\n  requirements: RequirementState[]\n  requireSecretRoom: boolean\n  secretRooms: SecretRoomName[]\n  artifacts: ArtifactName[]\n  maxDepth: number\n",
    "Plus QueryState fields",
)

s = replace_once(
    s,
    "export interface QueryDocument {\n  requirements: RequirementDocument[]\n  max_depth?: number\n",
    "export interface QueryDocument {\n  requirements: RequirementDocument[]\n  require_secret_room?: true\n  secret_rooms?: SecretRoomName[]\n  artifacts?: ArtifactName[]\n  max_depth?: number\n",
    "Plus QueryDocument fields",
)
write(rel, s)

# Query persistence / serialization / validation
rel = "web/src/lib/query.ts"
s = read(rel)

s = replace_once(
    s,
    "export const defaultQueryState = (): QueryState => ({\n  requirements: [],\n  maxDepth: 24,\n",
    "export const defaultQueryState = (): QueryState => ({\n  requirements: [],\n  requireSecretRoom: false,\n  secretRooms: [],\n  artifacts: [],\n  maxDepth: 24,\n",
    "Plus default query",
)

s = replace_once(
    s,
    "export function toQueryDocument(state: QueryState): QueryDocument {\n  const output: QueryDocument = { requirements: state.requirements.map(requirementToDocument) }\n  if (state.maxDepth !== 24) output.max_depth = state.maxDepth\n",
    "export function toQueryDocument(state: QueryState): QueryDocument {\n  const output: QueryDocument = { requirements: state.requirements.map(requirementToDocument) }\n  if (state.requireSecretRoom) output.require_secret_room = true\n  if (state.secretRooms.length) output.secret_rooms = [...state.secretRooms]\n  if (state.artifacts.length) output.artifacts = [...state.artifacts]\n  if (state.maxDepth !== 24) output.max_depth = state.maxDepth\n",
    "Plus serialization",
)

s = replace_once(
    s,
    "  return {\n    requirements: document.requirements.map(requirementFromDocument),\n    maxDepth: normalizeFloorLimit(document.max_depth ?? 24),\n",
    "  return {\n    requirements: document.requirements.map(requirementFromDocument),\n    requireSecretRoom: document.require_secret_room ?? false,\n    secretRooms: document.secret_rooms ? [...document.secret_rooms] : [],\n    artifacts: document.artifacts ? [...document.artifacts] : [],\n    maxDepth: normalizeFloorLimit(document.max_depth ?? 24),\n",
    "Plus hydration",
)

s = replace_once(
    s,
    "  if (!state.requirements.length) errors.push('Add at least one requirement.')\n  if (state.maxDepth < 1 || state.maxDepth > 24) errors.push('Maximum floor must be 1 through 24.')\n",
    "  const hasPlusRequirement = state.requireSecretRoom || state.secretRooms.length > 0 || state.artifacts.length > 0\n  if (!state.requirements.length && !hasPlusRequirement) errors.push('Add an item, secret-room, or artifact requirement.')\n  if (state.maxDepth < 1 || state.maxDepth > 24) errors.push('Maximum floor must be 1 through 24.')\n",
    "Plus validation",
)
write(rel, s)

# Query UI
rel = "web/src/designs/one/QueryPanel.tsx"
s = read(rel)

s = replace_once(
    s,
    "import type { AnalysisResult, ChallengeName, ItemCategory, QueryState, RequirementState, WandmakerQuest } from '../../lib/wasm/types'\n",
    "import type { AnalysisResult, ArtifactName, ChallengeName, ItemCategory, QueryState, RequirementState, SecretRoomName, WandmakerQuest } from '../../lib/wasm/types'\n",
    "Plus QueryPanel imports",
)

s = replace_once(
    s,
    "const LEVEL_GEN_CHALLENGES = new Set<ChallengeName>(['barren_land', 'into_darkness', 'forbidden_runes'])\n",
    """const LEVEL_GEN_CHALLENGES = new Set<ChallengeName>(['barren_land', 'into_darkness', 'forbidden_runes'])

const SECRET_ROOM_OPTIONS: readonly SecretRoomName[] = [
  'garden', 'laboratory', 'library', 'larder', 'well', 'runestone',
  'artillery', 'chest_chasm', 'honeypot', 'hoard', 'maze', 'summoning',
]

const ARTIFACT_OPTIONS: readonly ArtifactName[] = [
  'alchemists_toolkit', 'chalice_of_blood', 'cloak_of_shadows', 'dried_rose',
  'ethereal_chains', 'holy_tome', 'horn_of_plenty', 'master_thieves_armband',
  'sandals_of_nature', 'skeleton_key', 'talisman_of_foresight',
  'timekeepers_hourglass', 'unstable_spellbook',
]

const plusLabel = (value: string) =>
  value.split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
""",
    "Plus QueryPanel constants",
)

s = replace_once(
    s,
    "  const challengeCount = query.challenges.length\n  const wandmakerCount = Number(Boolean(query.wandmakerQuest))\n",
    "  const challengeCount = query.challenges.length\n  const plusSearchCount = Number(query.requireSecretRoom) + query.secretRooms.length + query.artifacts.length\n  const wandmakerCount = Number(Boolean(query.wandmakerQuest))\n",
    "Plus search count",
)

s = replace_once(
    s,
    "  const hasRequirements = query.requirements.length > 0\n",
    "  const hasRequirements = query.requirements.length > 0 || query.requireSecretRoom || query.secretRooms.length > 0 || query.artifacts.length > 0\n",
    "Plus hasRequirements",
)

search_scope_marker = """        <section className="d1-section">
          <div className="d1-section-head"><h3>Search scope</h3></div>
"""
plus_ui = """        <section className="d1-section">
          <details className="d1-details">
            <summary>
              <span>Secret rooms & artifacts</span>
              {plusSearchCount > 0 && <span className="d1-count">{plusSearchCount}</span>}
            </summary>
            <div className="d1-details-body">
              <label className="d1-check">
                <input
                  type="checkbox"
                  checked={query.requireSecretRoom}
                  onChange={(event) => patchQuery({ requireSecretRoom: event.currentTarget.checked })}
                />
                <span>Any secret room</span>
              </label>

              <div className="d1-plus-search-block">
                <div className="d1-field-label">Secret room types</div>
                <div className="d1-plus-search-grid">
                  {SECRET_ROOM_OPTIONS.map((room) => (
                    <label className="d1-check d1-plus-search-check" key={room}>
                      <input
                        type="checkbox"
                        checked={query.secretRooms.includes(room)}
                        onChange={(event) => patchQuery({
                          secretRooms: event.currentTarget.checked
                            ? [...query.secretRooms, room]
                            : query.secretRooms.filter((value) => value !== room),
                        })}
                      />
                      <span>{plusLabel(room)}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="d1-plus-search-block">
                <div className="d1-field-label">Artifacts</div>
                <div className="d1-plus-search-grid">
                  {ARTIFACT_OPTIONS.map((artifact) => (
                    <label className="d1-check d1-plus-search-check" key={artifact}>
                      <input
                        type="checkbox"
                        checked={query.artifacts.includes(artifact)}
                        onChange={(event) => patchQuery({
                          artifacts: event.currentTarget.checked
                            ? [...query.artifacts, artifact]
                            : query.artifacts.filter((value) => value !== artifact),
                        })}
                      />
                      <span>{plusLabel(artifact)}</span>
                    </label>
                  ))}
                </div>
              </div>

              <p className="d1-caption">
                Multiple selections use AND logic and the existing floor limit.
              </p>

              {plusSearchCount > 0 && (
                <button
                  type="button"
                  className="d1-btn d1-btn-sm"
                  onClick={() => patchQuery({ requireSecretRoom: false, secretRooms: [], artifacts: [] })}
                >
                  Clear rooms & artifacts
                </button>
              )}
            </div>
          </details>
        </section>

        <section className="d1-section">
          <div className="d1-section-head"><h3>Search scope</h3></div>
"""
s = replace_once(s, search_scope_marker, plus_ui, "Plus QueryPanel section")
write(rel, s)

# CSS
rel = "web/src/designs/one/styles.css"
s = read(rel)
s += """

/* SHPD-SEED-SEEKER-PLUS SEARCH V2.4 */
.d1-plus-search-block {
  margin-top: 14px;
}
.d1-plus-search-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 10px;
  margin-top: 5px;
}
.d1-plus-search-check {
  min-width: 0;
}
@media (max-width: 520px) {
  .d1-plus-search-grid {
    grid-template-columns: 1fr;
  }
}
"""
write(rel, s)

# WASM search adapter
rel = "crates/seedfinder-wasm/src/lib.rs"
s = read(rel)

s = replace_once(
    s,
    """use shpd_seedfinder_core::main_world::{
    CanonicalMainWorldGenerator, ConfiguredMainWorldGenerator, generate_main_world_with_challenges,
};
""",
    """use shpd_seedfinder_core::generator::ArtifactKind;
use shpd_seedfinder_core::main_world::{
    CanonicalMainWorldGenerator,
    ConfiguredMainWorldGenerator,
    generate_main_world_with_challenges,
    generate_scout_floor_metadata_with_challenges,
};
use shpd_seedfinder_core::room::SecretRoomKind;
""",
    "Plus WASM imports",
)

search_session_anchor = """/// Cooperative, single-threaded browser search state.
#[wasm_bindgen]
pub struct SearchSession {
"""
search_helpers = r"""// SHPD-SEED-SEEKER-PLUS SEARCH V2.4
#[derive(Clone, Default)]
struct PlusSearchFilters {
    require_secret_room: bool,
    secret_rooms: Vec<SecretRoomKind>,
    artifacts: Vec<ArtifactKind>,
    max_depth: u8,
    challenges: Challenges,
}

impl PlusSearchFilters {
    fn active(&self) -> bool {
        self.require_secret_room || !self.secret_rooms.is_empty() || !self.artifacts.is_empty()
    }

    fn matches_seed(&self, seed: DungeonSeed) -> bool {
        if !self.active() {
            return true;
        }
        let Ok(floors) = generate_scout_floor_metadata_with_challenges(
            seed,
            self.max_depth,
            self.challenges,
        ) else {
            return false;
        };

        if self.require_secret_room && !floors.iter().any(|floor| !floor.secret_rooms.is_empty()) {
            return false;
        }

        for wanted in &self.secret_rooms {
            if !floors.iter().any(|floor| {
                floor.secret_rooms.iter().any(|secret| secret.kind == *wanted)
            }) {
                return false;
            }
        }

        for wanted in &self.artifacts {
            if !floors.iter().any(|floor| floor.artifacts.contains(wanted)) {
                return false;
            }
        }

        true
    }
}

fn plus_secret_room(name: &str) -> Result<SecretRoomKind, String> {
    Ok(match name {
        "garden" => SecretRoomKind::Garden,
        "laboratory" => SecretRoomKind::Laboratory,
        "library" => SecretRoomKind::Library,
        "larder" => SecretRoomKind::Larder,
        "well" => SecretRoomKind::Well,
        "runestone" => SecretRoomKind::Runestone,
        "artillery" => SecretRoomKind::Artillery,
        "chest_chasm" => SecretRoomKind::ChestChasm,
        "honeypot" => SecretRoomKind::Honeypot,
        "hoard" => SecretRoomKind::Hoard,
        "maze" => SecretRoomKind::Maze,
        "summoning" => SecretRoomKind::Summoning,
        _ => return Err(format!("unknown secret room '{name}'")),
    })
}

fn plus_artifact(name: &str) -> Result<ArtifactKind, String> {
    Ok(match name {
        "alchemists_toolkit" => ArtifactKind::AlchemistsToolkit,
        "chalice_of_blood" => ArtifactKind::ChaliceOfBlood,
        "cloak_of_shadows" => ArtifactKind::CloakOfShadows,
        "dried_rose" => ArtifactKind::DriedRose,
        "ethereal_chains" => ArtifactKind::EtherealChains,
        "holy_tome" => ArtifactKind::HolyTome,
        "horn_of_plenty" => ArtifactKind::HornOfPlenty,
        "master_thieves_armband" => ArtifactKind::MasterThievesArmband,
        "sandals_of_nature" => ArtifactKind::SandalsOfNature,
        "skeleton_key" => ArtifactKind::SkeletonKey,
        "talisman_of_foresight" => ArtifactKind::TalismanOfForesight,
        "timekeepers_hourglass" => ArtifactKind::TimekeepersHourglass,
        "unstable_spellbook" => ArtifactKind::UnstableSpellbook,
        _ => return Err(format!("unknown artifact '{name}'")),
    })
}

fn split_plus_query(query_json: &str) -> Result<(String, PlusSearchFilters, bool), String> {
    let mut value: Value =
        serde_json::from_str(query_json).map_err(|error| format!("invalid JSON: {error}"))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| "query must be a JSON object".to_owned())?;

    let require_secret_room = object
        .remove("require_secret_room")
        .and_then(|value| value.as_bool())
        .unwrap_or(false);

    let secret_rooms = object
        .remove("secret_rooms")
        .map(|value| {
            value
                .as_array()
                .ok_or_else(|| "secret_rooms must be a list".to_owned())?
                .iter()
                .map(|value| {
                    value.as_str()
                        .ok_or_else(|| "secret room names must be strings".to_owned())
                        .and_then(plus_secret_room)
                })
                .collect::<Result<Vec<_>, _>>()
        })
        .transpose()?
        .unwrap_or_default();

    let artifacts = object
        .remove("artifacts")
        .map(|value| {
            value
                .as_array()
                .ok_or_else(|| "artifacts must be a list".to_owned())?
                .iter()
                .map(|value| {
                    value.as_str()
                        .ok_or_else(|| "artifact names must be strings".to_owned())
                        .and_then(plus_artifact)
                })
                .collect::<Result<Vec<_>, _>>()
        })
        .transpose()?
        .unwrap_or_default();

    let max_depth = object.get("max_depth").and_then(Value::as_u64).unwrap_or(24);
    let max_depth = u8::try_from(max_depth).map_err(|_| "max_depth is too large".to_owned())?;
    if !(1..=24).contains(&max_depth) {
        return Err("max_depth must be 1 through 24".to_owned());
    }

    let challenges = object
        .get("challenges")
        .cloned()
        .map(|value| {
            serde_json::from_value::<Vec<FileChallenge>>(value)
                .map(|items| items.into_iter().fold(Challenges::NONE, |mask, item| mask | item.into()))
                .map_err(|error| format!("invalid challenges: {error}"))
        })
        .transpose()?
        .unwrap_or(Challenges::NONE);

    let has_items = object
        .get("requirements")
        .and_then(Value::as_array)
        .is_some_and(|requirements| !requirements.is_empty());

    Ok((
        value.to_string(),
        PlusSearchFilters {
            require_secret_room,
            secret_rooms,
            artifacts,
            max_depth,
            challenges,
        },
        has_items,
    ))
}

/// Cooperative, single-threaded browser search state.
#[wasm_bindgen]
pub struct SearchSession {
"""
s = replace_once(s, search_session_anchor, search_helpers, "Plus WASM search helpers")

s = replace_once(
    s,
    """pub struct SearchSession {
    query: SearchQuery,
    plan: QueryPlan,
    generator: ConfiguredMainWorldGenerator,
""",
    """pub struct SearchSession {
    query: Option<SearchQuery>,
    plan: Option<QueryPlan>,
    plus: PlusSearchFilters,
    generator: ConfiguredMainWorldGenerator,
""",
    "Plus SearchSession fields",
)

s = replace_once(
    s,
    """            let worlds = self.generator.generate_batch_gated(
                &seeds,
                self.plan.generation_depth(),
                &self.plan,
            );
            for world in worlds {
                self.cursor += 1;
                self.tested += 1;
                if let Some(world) = world
                    && self.query.matches(&world)
                {
                    matches.push(world.seed.into());
                    self.accepted += 1;
                    if self.accepted == MAX_RESULTS {
                        self.completed = true;
                        break;
                    }
                }
            }
""",
    """            if let (Some(query), Some(plan)) = (&self.query, &self.plan) {
                let worlds = self.generator.generate_batch_gated(
                    &seeds,
                    plan.generation_depth(),
                    plan,
                );
                for world in worlds {
                    self.cursor += 1;
                    self.tested += 1;
                    if let Some(world) = world
                        && query.matches(&world)
                        && self.plus.matches_seed(world.seed)
                    {
                        matches.push(world.seed.into());
                        self.accepted += 1;
                        if self.accepted == MAX_RESULTS {
                            self.completed = true;
                            break;
                        }
                    }
                }
            } else {
                for seed in seeds {
                    self.cursor += 1;
                    self.tested += 1;
                    if self.plus.matches_seed(seed) {
                        matches.push(seed.into());
                        self.accepted += 1;
                        if self.accepted == MAX_RESULTS {
                            self.completed = true;
                            break;
                        }
                    }
                }
            }
""",
    "Plus SearchSession advance",
)

s = replace_once(
    s,
    """        let query = json_query::decode(query_json)?;
        let start_seed = seed_bound(start_seed, false)?;
""",
    """        let (clean_json, plus, has_items) = split_plus_query(query_json)?;
        if !has_items && !plus.active() {
            return Err("add an item, secret-room, or artifact requirement".to_owned());
        }
        let query = has_items.then(|| json_query::decode(&clean_json)).transpose()?;
        let start_seed = seed_bound(start_seed, false)?;
""",
    "Plus SearchSession decode",
)

s = replace_once(
    s,
    """        let plan = QueryPlan::analyze(&query);
        let completed = plan.is_unsatisfiable();
        Ok(Self {
            generator: CanonicalMainWorldGenerator::with_challenges(query.challenges),
            query,
            plan,
""",
    """        let plan = query.as_ref().map(QueryPlan::analyze);
        let completed = plan.as_ref().is_some_and(QueryPlan::is_unsatisfiable);
        let challenges = query.as_ref().map_or(plus.challenges, |query| query.challenges);
        Ok(Self {
            generator: CanonicalMainWorldGenerator::with_challenges(challenges),
            query,
            plan,
            plus,
""",
    "Plus SearchSession state",
)

# analyze_query
s = replace_once(
    s,
    """pub fn analyze_query(query_json: &str) -> String {
    let query = match json_query::decode(query_json) {
        Ok(query) => query,
        Err(error) => {
""",
    """pub fn analyze_query(query_json: &str) -> String {
    let (clean_json, plus, has_items) = match split_plus_query(query_json) {
        Ok(parts) => parts,
        Err(error) => {
            return to_json(&AnalysisOutput::Invalid { valid: false, error });
        }
    };
    if !has_items && plus.active() {
        return to_json(&AnalysisOutput::Valid {
            valid: true,
            probability: None,
            impossible: false,
            notes: Vec::new(),
        });
    }
    let query = match json_query::decode(&clean_json) {
        Ok(query) => query,
        Err(error) => {
""",
    "Plus analyze_query",
)

# scout query
s = replace_once(
    s,
    """    let query = request
        .query
        .map(|value| json_query::decode(&value.to_string()))
        .transpose()?;
""",
    """    let query = request
        .query
        .map(|value| {
            let (clean_json, _plus, has_items) = split_plus_query(&value.to_string())?;
            has_items.then(|| json_query::decode(&clean_json)).transpose()
        })
        .transpose()?
        .flatten();
""",
    "Plus scout query",
)

# filter/refine
s = replace_once(
    s,
    """fn filter_seeds_impl(query_json: &str, seed_values: &[f64]) -> Result<String, String> {
    let query = json_query::decode(query_json)?;
    let seeds = seed_values
""",
    """fn filter_seeds_impl(query_json: &str, seed_values: &[f64]) -> Result<String, String> {
    let (clean_json, plus, has_items) = split_plus_query(query_json)?;
    let query = has_items.then(|| json_query::decode(&clean_json)).transpose()?;
    let seeds = seed_values
""",
    "Plus filter decode",
)

s = replace_once(
    s,
    """    let plan = QueryPlan::analyze(&query);
    if plan.is_unsatisfiable() {
        return Ok(to_json::<Vec<SeedOutput>>(&Vec::new()));
    }
    let generator = CanonicalMainWorldGenerator::with_challenges(query.challenges);
    let worlds = generator.generate_batch_gated(&seeds, plan.generation_depth(), &plan);
    let matches = worlds
        .into_iter()
        .flatten()
        .filter(|world| query.matches(world))
        .map(|world| SeedOutput::from(world.seed))
        .collect::<Vec<_>>();
    Ok(to_json(&matches))
""",
    """    let matches = if let Some(query) = query {
        let plan = QueryPlan::analyze(&query);
        if plan.is_unsatisfiable() {
            return Ok(to_json::<Vec<SeedOutput>>(&Vec::new()));
        }
        let generator = CanonicalMainWorldGenerator::with_challenges(query.challenges);
        generator
            .generate_batch_gated(&seeds, plan.generation_depth(), &plan)
            .into_iter()
            .flatten()
            .filter(|world| query.matches(world) && plus.matches_seed(world.seed))
            .map(|world| SeedOutput::from(world.seed))
            .collect::<Vec<_>>()
    } else {
        seeds
            .into_iter()
            .filter(|seed| plus.matches_seed(*seed))
            .map(SeedOutput::from)
            .collect::<Vec<_>>()
    };
    Ok(to_json(&matches))
""",
    "Plus filter matcher",
)

# Safe refine behaviour
s = replace_once(
    s,
    """fn query_continues_impl(candidate_json: &str, base_json: &str) -> Result<bool, String> {
    Ok(json_query::decode(candidate_json)?.continues(&json_query::decode(base_json)?))
}
""",
    """fn query_continues_impl(candidate_json: &str, base_json: &str) -> Result<bool, String> {
    let (candidate_clean, candidate_plus, candidate_has_items) = split_plus_query(candidate_json)?;
    let (base_clean, base_plus, base_has_items) = split_plus_query(base_json)?;
    if candidate_plus.active() || base_plus.active() || !candidate_has_items || !base_has_items {
        return Ok(false);
    }
    Ok(json_query::decode(&candidate_clean)?.continues(&json_query::decode(&base_clean)?))
}
""",
    "Plus query continuation",
)
write(rel, s)


# ===========================================================================
# 8. CLEAN SCOUT DISPLAY — V2.5
# ===========================================================================
# Do not show empty floor cards, "Secret rooms: No (0)", or "Artifacts: None".
# A floor remains visible if it contains:
#   - at least one normal searchable item, OR
#   - at least one secret room, OR
#   - at least one artifact.

rel = "web/src/designs/one/ScoutPanel.tsx"
s = read(rel)

# Filter metadata-backed floor cards so totally empty floors disappear.
old = """    return metadata
      .map((metadata) => ({
        depth: metadata.depth,
        items: byDepth.get(metadata.depth) ?? [],
        metadata,
      }))
      .sort((left, right) => Number(left.depth) - Number(right.depth))
"""
new = """    return metadata
      .map((metadata) => ({
        depth: metadata.depth,
        items: byDepth.get(metadata.depth) ?? [],
        metadata,
      }))
      .filter(({ items, metadata }) =>
        items.length > 0 ||
        metadata.secretRooms.length > 0 ||
        metadata.artifacts.length > 0
      )
      .sort((left, right) => Number(left.depth) - Number(right.depth))
"""
s = replace_once(s, old, new, "empty Scout floor filtering")

# Hide the Secret Rooms heading entirely when there are no secrets.
old = """                      <div className="d1-plus-floor-meta-row">
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
"""
new = """                      {secretCount > 0 && (
                        <>
                          <div className="d1-plus-floor-meta-row">
                            <span className="d1-plus-floor-meta-label">Secret rooms</span>
                            <b>Yes ({secretCount})</b>
                          </div>
                          {metadata.secretRooms.map((secret, index) => (
                            <div
                              className="d1-plus-secret-line"
                              key={`${secret.kind}-${secret.room}-${secret.wall}-${index}`}
                            >
                              {secretRoomSummary(secret)}
                            </div>
                          ))}
                        </>
                      )}
"""
s = replace_once(s, old, new, "empty Secret Rooms row removal")

# Hide Artifacts entirely when there are none.
old = """                      <div className="d1-plus-floor-meta-row d1-plus-artifact-row">
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
"""
new = """                      {metadata.artifacts.length > 0 && (
                        <div className="d1-plus-floor-meta-row d1-plus-artifact-row">
                          <span className="d1-plus-floor-meta-label">Artifacts</span>
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
                        </div>
                      )}
"""
s = replace_once(s, old, new, "empty Artifacts row removal")

# Avoid an empty metadata wrapper on item-only floors.
old = """                  {metadata && (
                    <div className="d1-plus-floor-meta">
"""
new = """                  {metadata && (secretCount > 0 || metadata.artifacts.length > 0) && (
                    <div className="d1-plus-floor-meta">
"""
s = replace_once(s, old, new, "empty metadata wrapper removal")

write(rel, s)

print("Seed Seeker Plus V2.5 clean Scout display applied successfully.")
