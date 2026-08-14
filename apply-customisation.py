#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: apply-customisation.py PATH_TO_UPSTREAM_APP")

root = Path(sys.argv[1]).resolve()
MARKER = "SHPD-SEED-SEEKER-PLUS"

def read(rel):
    return (root / rel).read_text(encoding="utf-8")

def write(rel, text):
    (root / rel).write_text(text, encoding="utf-8")

def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Could not find {label}. Upstream source may have changed.")
    return text.replace(old, new, 1)

# CORE
rel = "crates/seedfinder-core/src/main_world.rs"
s = read(rel)
if MARKER not in s:
    s = replace_once(s, "use crate::challenges::Challenges;\n",
        "use crate::challenges::Challenges;\nuse crate::generator::{ARTIFACT_ITEMS, ArtifactKind};\n",
        "core import 1")
    s = replace_once(s, "use crate::rng::{RandomStack, seed_for_depth};\n",
        "use crate::rng::{RandomStack, seed_for_depth};\nuse crate::room::{Room, RoomKind, SecretRoomKind};\n",
        "core import 2")
    s = replace_once(s, "use crate::run::RunState;\n",
        "use crate::run::{GeneratorCategory, RunState};\n",
        "core import 3")

    block = r'''
/// SHPD-SEED-SEEKER-PLUS
#[derive(Clone, Debug, PartialEq)]
pub struct ScoutFloorMetadata {
    pub depth: u8,
    pub secret_rooms: Vec<SecretRoomKind>,
    pub artifacts: Vec<ArtifactKind>,
}

fn scout_artifact_snapshot(run: &RunState) -> Vec<f32> {
    run.generator
        .category(GeneratorCategory::Artifact)
        .probabilities
        .as_slice()
        .to_vec()
}

fn scout_artifacts_generated(before: &[f32], after: &[f32]) -> Vec<ArtifactKind> {
    before.iter()
        .zip(after.iter())
        .zip(ARTIFACT_ITEMS.iter())
        .filter_map(|((&before_probability, &after_probability), &artifact)| {
            (before_probability > 0.0 && after_probability == 0.0).then_some(artifact)
        })
        .collect()
}

fn scout_secret_rooms(rooms: &[Room]) -> Vec<SecretRoomKind> {
    rooms.iter()
        .filter_map(|room| match room.kind {
            RoomKind::Secret(kind) => Some(kind),
            _ => None,
        })
        .collect()
}

/// Scout-only replay of canonical generation. No extra RNG draws are made.
pub fn generate_scout_floor_metadata_with_challenges(
    seed: DungeonSeed,
    maximum_depth: u8,
    challenges: Challenges,
) -> Result<Vec<ScoutFloorMetadata>, MainWorldError> {
    if !(1..=24).contains(&maximum_depth) {
        return Err(MainWorldError::InvalidMaximumDepth(maximum_depth));
    }

    let target = effective_regular_depth(maximum_depth);
    let dungeon_seed = i64::try_from(seed.value()).expect("base-26 seed range fits Java long");
    let roots = regular_depths(target)
        .map(|depth| seed_for_depth(dungeon_seed, depth, 0))
        .collect::<Vec<_>>();

    let mut run = RunState::with_challenges(dungeon_seed, challenges);
    let mut limited_drops = LimitedDrops::default();
    let mut quests = QuestState::new();
    let mut shop_run = ShopRunState::default();
    let mut random = RandomStack::with_base_seed(0);
    let mut output = Vec::with_capacity(usize::from(maximum_depth));

    for (&root, depth) in roots.iter().zip(regular_depths(target)) {
        random.push(root);
        let artifacts_before = scout_artifact_snapshot(&run);

        let secret_rooms = match depth {
            1..=4 => {
                let floor = generate_sewer_floor(
                    &mut run, &mut limited_drops, &mut quests, depth, &mut random
                ).map_err(MainWorldError::Sewer)?;
                scout_secret_rooms(&floor.painted.rooms)
            }
            6..=9 => {
                let floor = generate_prison_floor(
                    &mut run, &mut limited_drops, &mut quests, &mut shop_run, depth, &mut random
                ).map_err(MainWorldError::Prison)?;
                scout_secret_rooms(&floor.painted.rooms)
            }
            11..=14 => {
                let floor = generate_caves_floor(
                    &mut run, &mut limited_drops, &mut quests, &mut shop_run, depth, &mut random
                ).map_err(MainWorldError::Caves)?;
                scout_secret_rooms(&floor.painted.rooms)
            }
            16..=19 => {
                let floor = generate_city_floor(
                    &mut run, &mut limited_drops, &mut quests, &mut shop_run, depth, &mut random
                ).map_err(MainWorldError::City)?;
                scout_secret_rooms(&floor.painted.rooms)
            }
            20 => {
                let _ = generate_city_boss_shop(&mut run, &mut shop_run, &mut random)
                    .map_err(|error| MainWorldError::Halls(HallsFloorError::BossShop(error)))?;
                Vec::new()
            }
            _ => {
                let floor = generate_halls_floor(
                    &mut run, &mut limited_drops, &mut quests, &mut shop_run, depth, &mut random
                ).map_err(MainWorldError::Halls)?;
                scout_secret_rooms(&floor.painted.rooms)
            }
        };

        let artifacts_after = scout_artifact_snapshot(&run);
        random.pop();

        output.push(ScoutFloorMetadata {
            depth: u8::try_from(depth).expect("main-path depths fit u8"),
            secret_rooms,
            artifacts: scout_artifacts_generated(&artifacts_before, &artifacts_after),
        });
    }

    for depth in [5_u8, 10, 15] {
        if depth <= maximum_depth {
            output.push(ScoutFloorMetadata {
                depth,
                secret_rooms: Vec::new(),
                artifacts: Vec::new(),
            });
        }
    }

    output.retain(|floor| floor.depth <= maximum_depth);
    output.sort_by_key(|floor| floor.depth);
    Ok(output)
}

'''
    s = replace_once(
        s,
        "/// Failure while producing a canonical main-dungeon prefix.\n",
        block + "/// Failure while producing a canonical main-dungeon prefix.\n",
        "core insertion point")
    write(rel, s)

# WASM
rel = "crates/seedfinder-wasm/src/lib.rs"
s = read(rel)
if MARKER not in s:
    s = replace_once(
        s,
        '''struct ScoutOutput {
    seed: SeedOutput,
    quests: Vec<ScoutQuestOutput>,
    items: Vec<ScoutItemOutput>,
    matched_requirements: usize,
    total_requirements: usize,
}
''',
        '''struct ScoutOutput {
    seed: SeedOutput,
    quests: Vec<ScoutQuestOutput>,
    items: Vec<ScoutItemOutput>,
    floors: Vec<ScoutFloorOutput>,
    matched_requirements: usize,
    total_requirements: usize,
}
''',
        "WASM ScoutOutput")

    block = r'''
/// SHPD-SEED-SEEKER-PLUS
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ScoutFloorOutput {
    depth: u8,
    secret_rooms: Vec<&'static str>,
    artifacts: Vec<&'static str>,
}

const fn scout_secret_room_name(kind: shpd_seedfinder_core::room::SecretRoomKind) -> &'static str {
    use shpd_seedfinder_core::room::SecretRoomKind;
    match kind {
        SecretRoomKind::Garden => "garden",
        SecretRoomKind::Laboratory => "laboratory",
        SecretRoomKind::Library => "library",
        SecretRoomKind::Larder => "larder",
        SecretRoomKind::Well => "well",
        SecretRoomKind::Runestone => "runestone",
        SecretRoomKind::Artillery => "artillery",
        SecretRoomKind::ChestChasm => "chest_chasm",
        SecretRoomKind::Honeypot => "honeypot",
        SecretRoomKind::Hoard => "hoard",
        SecretRoomKind::Maze => "maze",
        SecretRoomKind::Summoning => "summoning",
    }
}

const fn scout_artifact_name(kind: shpd_seedfinder_core::generator::ArtifactKind) -> &'static str {
    use shpd_seedfinder_core::generator::ArtifactKind;
    match kind {
        ArtifactKind::AlchemistsToolkit => "alchemists_toolkit",
        ArtifactKind::ChaliceOfBlood => "chalice_of_blood",
        ArtifactKind::CloakOfShadows => "cloak_of_shadows",
        ArtifactKind::DriedRose => "dried_rose",
        ArtifactKind::EtherealChains => "ethereal_chains",
        ArtifactKind::HolyTome => "holy_tome",
        ArtifactKind::HornOfPlenty => "horn_of_plenty",
        ArtifactKind::MasterThievesArmband => "master_thieves_armband",
        ArtifactKind::SandalsOfNature => "sandals_of_nature",
        ArtifactKind::SkeletonKey => "skeleton_key",
        ArtifactKind::TalismanOfForesight => "talisman_of_foresight",
        ArtifactKind::TimekeepersHourglass => "timekeepers_hourglass",
        ArtifactKind::UnstableSpellbook => "unstable_spellbook",
    }
}

'''
    s = replace_once(
        s,
        '''#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ScoutQuestOutput {
''',
        block + '''#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ScoutQuestOutput {
''',
        "WASM insertion point")

    s = replace_once(
        s,
        '''    let world = generate_main_world_with_challenges(seed, 24, challenges)
        .map_err(|error| format!("world generation failed: {error}"))?;
''',
        '''    let world = generate_main_world_with_challenges(seed, 24, challenges)
        .map_err(|error| format!("world generation failed: {error}"))?;
    let floors =
        shpd_seedfinder_core::main_world::generate_scout_floor_metadata_with_challenges(
            seed, 24, challenges,
        )
        .map_err(|error| format!("scout metadata generation failed: {error}"))?
        .into_iter()
        .map(|floor| ScoutFloorOutput {
            depth: floor.depth,
            secret_rooms: floor.secret_rooms.into_iter().map(scout_secret_room_name).collect(),
            artifacts: floor.artifacts.into_iter().map(scout_artifact_name).collect(),
        })
        .collect();
''',
        "WASM scout generation")

    s = replace_once(
        s,
        '''        quests: scout_quest_outputs(world.quests),
        items,
        matched_requirements,
''',
        '''        quests: scout_quest_outputs(world.quests),
        items,
        floors,
        matched_requirements,
''',
        "WASM output")
    write(rel, s)

# TYPESCRIPT
rel = "web/src/lib/wasm/types.ts"
s = read(rel)
if MARKER not in s:
    block = r'''
// SHPD-SEED-SEEKER-PLUS
export type SecretRoomName =
  | 'garden' | 'laboratory' | 'library' | 'larder' | 'well' | 'runestone'
  | 'artillery' | 'chest_chasm' | 'honeypot' | 'hoard' | 'maze' | 'summoning'

export type ArtifactName =
  | 'alchemists_toolkit' | 'chalice_of_blood' | 'cloak_of_shadows' | 'dried_rose'
  | 'ethereal_chains' | 'holy_tome' | 'horn_of_plenty' | 'master_thieves_armband'
  | 'sandals_of_nature' | 'skeleton_key' | 'talisman_of_foresight'
  | 'timekeepers_hourglass' | 'unstable_spellbook'

export interface ScoutFloor {
  depth: number
  secretRooms: SecretRoomName[]
  artifacts: ArtifactName[]
}

'''
    s = replace_once(s, "export interface ScoutResult {\n",
                     block + "export interface ScoutResult {\n",
                     "TS ScoutResult")
    s = replace_once(
        s,
        '''  items: ScoutItem[]
  quests: ScoutQuest[]
  matchedRequirements: number
''',
        '''  items: ScoutItem[]
  quests: ScoutQuest[]
  floors?: ScoutFloor[]
  matchedRequirements: number
''',
        "TS fields")
    write(rel, s)

# UI
rel = "web/src/designs/one/ScoutPanel.tsx"
s = read(rel)
if MARKER not in s:
    s = replace_once(
        s,
        "import type { ScoutItem, ScoutResult } from '../../lib/wasm/types'\n",
        '''import type {
  ArtifactName,
  ScoutItem,
  ScoutResult,
  SecretRoomName,
} from '../../lib/wasm/types'
''',
        "UI import")

    helpers = r'''
// SHPD-SEED-SEEKER-PLUS
const prettyScoutToken = (value: string) =>
  value.split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
const secretRoomLabel = (value: SecretRoomName) => prettyScoutToken(value)
const artifactLabel = (value: ArtifactName) => prettyScoutToken(value)

'''
    s = replace_once(
        s,
        "const groupLetter = (group: number) => 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[group % 26]\n",
        "const groupLetter = (group: number) => 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[group % 26]\n" + helpers,
        "UI helpers")

    s = replace_once(
        s,
        "    return [...byDepth.entries()].sort(([left], [right]) => left - right)\n",
        '''    const metadata = result?.floors ?? []
    if (metadata.length === 0) {
      return [...byDepth.entries()]
        .sort(([left], [right]) => left - right)
        .map(([depth, items]) => ({ depth, items, metadata: undefined }))
    }
    return metadata
      .map((metadata) => ({
        depth: metadata.depth,
        items: byDepth.get(metadata.depth) ?? [],
        metadata,
      }))
      .sort((left, right) => Number(left.depth) - Number(right.depth))
      ''',
        "UI floor grouping")

    s = replace_once(
        s,
        '''                {result.items.length} item{result.items.length === 1 ? '' : 's'} across {floors.length} floor{floors.length === 1 ? '' : 's'}
''',
        '''                {result.items.length} searchable item{result.items.length === 1 ? '' : 's'} · {floors.length} floors scouted
''',
        "UI caption")

    s = replace_once(
        s,
        '''            {floors.map(([depth, items]) => {
              const region = regionForDepth(depth)
              const quest = questByDepth.get(depth)
''',
        '''            {floors.map(({ depth, items, metadata }) => {
              const region = regionForDepth(depth)
              const quest = questByDepth.get(depth)
              const secretCount = metadata?.secretRooms.length ?? 0
''',
        "UI floor map")

    s = replace_once(
        s,
        '''                  </header>
                  <ul className="d1-item-list">
''',
        '''                  </header>
                  {metadata && (
                    <div className="d1-plus-floor-meta">
                      <div className="d1-plus-floor-meta-row">
                        <span className="d1-plus-floor-meta-label">Secret rooms</span>
                        <b>{secretCount > 0 ? `Yes (${secretCount})` : 'No (0)'}</b>
                        {secretCount > 0 && (
                          <span>{metadata.secretRooms.map(secretRoomLabel).join(', ')}</span>
                        )}
                      </div>
                      <div className="d1-plus-floor-meta-row">
                        <span className="d1-plus-floor-meta-label">Artifacts</span>
                        <b>{metadata.artifacts.length > 0 ? metadata.artifacts.length : 'None'}</b>
                        {metadata.artifacts.length > 0 && (
                          <span>{metadata.artifacts.map(artifactLabel).join(', ')}</span>
                        )}
                      </div>
                    </div>
                  )}
                  <ul className="d1-item-list">
''',
        "UI metadata")
    write(rel, s)

# CSS
rel = "web/src/designs/one/styles.css"
s = read(rel)
if MARKER not in s:
    s += r'''

/* SHPD-SEED-SEEKER-PLUS */
.d1-plus-floor-meta {
  display: grid;
  gap: 5px;
  padding: 8px 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--region) 22%, transparent);
  font-size: 12px;
}
.d1-plus-floor-meta-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 10px;
}
.d1-plus-floor-meta-label {
  min-width: 82px;
  opacity: 0.72;
}
.d1-plus-floor-meta-row > span:last-child {
  opacity: 0.78;
}
'''
    write(rel, s)

print("SHPD Seed Seeker Plus customisation applied successfully.")
