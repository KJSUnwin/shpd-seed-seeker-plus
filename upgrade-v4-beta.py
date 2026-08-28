#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 3 or sys.argv[1] not in {"shared", "beta"}:
    raise SystemExit("Usage: upgrade-v4-beta.py shared|beta PATH_TO_APP")
mode = sys.argv[1]
root = Path(sys.argv[2]).resolve()

def read(rel): return (root / rel).read_text(encoding="utf-8")
def write(rel, text): (root / rel).write_text(text, encoding="utf-8")
def once(text, old, new, label):
    if new in text: return text
    if old not in text: raise RuntimeError(f"Could not find {label}; source/customisation version drifted.")
    return text.replace(old, new, 1)
def regex_once(text, pattern, replacement, label):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1: raise RuntimeError(f"Could not patch {label}; matched {count} times.")
    return updated

if mode == "shared":
    # ---- Core metadata: Catalyst floor + four deterministic choices ----
    rel = "crates/seedfinder-core/src/main_world.rs"; s = read(rel)
    if "SHPD-TRINKET-SCOUT-V1" not in s:
        s = once(s,
            "use crate::generator::{ARTIFACT_ITEMS, ArtifactKind};",
            "use crate::generator::{ARTIFACT_ITEMS, ArtifactKind, GeneratedItem, TrinketKind, random_category};",
            "main-world generator import")
        s = once(s,
            "    pub artifacts: Vec<ArtifactKind>,\n}",
            "    pub artifacts: Vec<ArtifactKind>,\n    /// SHPD-TRINKET-SCOUT-V1\n    pub trinket_choices: Vec<TrinketKind>,\n}",
            "ScoutFloorMetadata trinkets field")
        anchor = "fn scout_artifacts_generated(before: &[f32], after: &[f32]) -> Vec<ArtifactKind> {"
        i = s.find(anchor)
        if i < 0: raise RuntimeError("Could not find scout artifact helper")
        helper = '''/// SHPD-TRINKET-SCOUT-V1
fn scout_trinket_choices(dungeon_seed: i64, challenges: Challenges) -> Vec<TrinketKind> {
    let mut run = RunState::with_challenges(dungeon_seed, challenges);
    let mut outer = RandomStack::with_base_seed(0);
    let mut choices = Vec::with_capacity(4);
    while choices.len() < 4 {
        match random_category(&mut outer, &mut run.generator, GeneratorCategory::Trinket, 1) {
            Ok(GeneratedItem::Trinket(kind)) => choices.push(kind),
            Ok(_) | Err(_) => break,
        }
    }
    choices
}

'''
        s = s[:i] + helper + s[i:]
        s = once(s,
            "    let mut output = Vec::with_capacity(usize::from(maximum_depth));\n",
            "    let mut output = Vec::with_capacity(usize::from(maximum_depth));\n    let catalyst_choices = scout_trinket_choices(dungeon_seed, challenges);\n",
            "Scout output init")
        s = once(s,
            "        let artifacts_before = scout_artifact_snapshot(&run);\n",
            "        let artifacts_before = scout_artifact_snapshot(&run);\n        let catalyst_before = limited_drops.trinket_catalyst_dropped;\n",
            "catalyst before snapshot")
        s = once(s,
            "        let artifacts_after = scout_artifact_snapshot(&run);\n",
            "        let artifacts_after = scout_artifact_snapshot(&run);\n        let catalyst_on_this_floor = !catalyst_before && limited_drops.trinket_catalyst_dropped;\n",
            "catalyst after snapshot")
        s = once(s,
            "            artifacts: scout_artifacts_generated(&artifacts_before, &artifacts_after),\n",
            "            artifacts: scout_artifacts_generated(&artifacts_before, &artifacts_after),\n            trinket_choices: if catalyst_on_this_floor { catalyst_choices.clone() } else { Vec::new() },\n",
            "ordinary ScoutFloorMetadata output")
        # Boss floors are created in a separate small block.
        s = s.replace(
            "                artifacts: Vec::new(),\n            });",
            "                artifacts: Vec::new(),\n                trinket_choices: Vec::new(),\n            });")
        write(rel, s)

    # ---- WASM ----
    rel = "crates/seedfinder-wasm/src/lib.rs"; s = read(rel)
    if "SHPD-TRINKET-SCOUT-V1" not in s:
        s = once(s,
            "    artifacts: Vec<&'static str>,\n}",
            "    artifacts: Vec<&'static str>,\n    /// SHPD-TRINKET-SCOUT-V1\n    trinket_choices: Vec<&'static str>,\n}",
            "WASM ScoutFloorOutput")
        idx = s.find("const fn scout_artifact_name(")
        if idx < 0: raise RuntimeError("Could not find scout_artifact_name")
        trinket_fn = '''/// SHPD-TRINKET-SCOUT-V1
const fn scout_trinket_name(kind: shpd_seedfinder_core::generator::TrinketKind) -> &'static str {
    use shpd_seedfinder_core::generator::TrinketKind;
    match kind {
        TrinketKind::RatSkull => "rat_skull",
        TrinketKind::ParchmentScrap => "parchment_scrap",
        TrinketKind::PetrifiedSeed => "petrified_seed",
        TrinketKind::ExoticCrystals => "exotic_crystals",
        TrinketKind::MossyClump => "mossy_clump",
        TrinketKind::DimensionalSundial => "dimensional_sundial",
        TrinketKind::ThirteenLeafClover => "thirteen_leaf_clover",
        TrinketKind::TrapMechanism => "trap_mechanism",
        TrinketKind::MimicTooth => "mimic_tooth",
        TrinketKind::WondrousResin => "wondrous_resin",
        TrinketKind::EyeOfNewt => "eye_of_newt",
        TrinketKind::SaltCube => "salt_cube",
        TrinketKind::VialOfBlood => "vial_of_blood",
        TrinketKind::ShardOfOblivion => "shard_of_oblivion",
        TrinketKind::ChaoticCenser => "chaotic_censer",
        TrinketKind::FerretTuft => "ferret_tuft",
        TrinketKind::CrackedSpyglass => "cracked_spyglass",
    }
}

'''
        s = s[:idx] + trinket_fn + s[idx:]
        s = once(s,
            "            artifacts: floor.artifacts.into_iter().map(scout_artifact_name).collect(),\n",
            "            artifacts: floor.artifacts.into_iter().map(scout_artifact_name).collect(),\n            trinket_choices: floor.trinket_choices.into_iter().map(scout_trinket_name).collect(),\n",
            "WASM trinket mapping")
        write(rel, s)

    # ---- TypeScript ----
    rel = "web/src/lib/wasm/types.ts"; s = read(rel)
    if "SHPD-TRINKET-SCOUT-V1" not in s:
        idx = s.find("export interface ScoutFloor {")
        if idx < 0: raise RuntimeError("Could not find ScoutFloor interface")
        tt = '''// SHPD-TRINKET-SCOUT-V1
export type TrinketName =
  | 'rat_skull' | 'parchment_scrap' | 'petrified_seed' | 'exotic_crystals'
  | 'mossy_clump' | 'dimensional_sundial' | 'thirteen_leaf_clover'
  | 'trap_mechanism' | 'mimic_tooth' | 'wondrous_resin' | 'eye_of_newt'
  | 'salt_cube' | 'vial_of_blood' | 'shard_of_oblivion' | 'chaotic_censer'
  | 'ferret_tuft' | 'cracked_spyglass'

'''
        s = s[:idx] + tt + s[idx:]
        s = once(s,
            "  artifacts: ArtifactName[]\n}",
            "  artifacts: ArtifactName[]\n  trinketChoices: TrinketName[]\n}",
            "ScoutFloor trinketChoices")
        write(rel, s)

    # ---- Scout UI ----
    rel = "web/src/designs/one/ScoutPanel.tsx"; s = read(rel)
    if "SHPD-TRINKET-SCOUT-V1" not in s:
        s = once(s, "  SecretRoomName,\n", "  SecretRoomName,\n  TrinketName,\n", "TrinketName import")
        s = once(s,
            "const artifactLabel = (value: ArtifactName) => prettyScoutToken(value)\n",
            "const artifactLabel = (value: ArtifactName) => prettyScoutToken(value)\n// SHPD-TRINKET-SCOUT-V1\nconst trinketLabel = (value: TrinketName) => prettyScoutToken(value)\n",
            "trinket label")
        s = once(s,
            "        metadata.artifacts.length > 0\n",
            "        metadata.artifacts.length > 0 ||\n        metadata.trinketChoices.length > 0\n",
            "empty-floor retention")
        s = once(s,
            "                  {metadata && (secretCount > 0 || metadata.artifacts.length > 0) && (\n",
            "                  {metadata && (secretCount > 0 || metadata.artifacts.length > 0 || metadata.trinketChoices.length > 0) && (\n",
            "metadata wrapper")
        artifact_block = '''                      {metadata.artifacts.length > 0 && (
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
'''
        if artifact_block not in s: raise RuntimeError("Could not find clean artifact UI block")
        trinket_block = artifact_block + '''                      {metadata.trinketChoices.length > 0 && (
                        <div className="d1-plus-floor-meta-row d1-plus-trinket-row">
                          <span className="d1-plus-floor-meta-label">Trinket Catalyst</span>
                          <div>
                            <b>4 choices</b>
                            <span className="d1-plus-trinket-choices">
                              {metadata.trinketChoices.map(trinketLabel).join(' · ')}
                            </span>
                          </div>
                        </div>
                      )}
'''
        s = s.replace(artifact_block, trinket_block, 1)
        write(rel, s)

    rel = "web/src/designs/one/styles.css"; s = read(rel)
    if "SHPD-TRINKET-SCOUT-V1" not in s:
        s += '''
/* SHPD-TRINKET-SCOUT-V1 */
.d1-plus-trinket-row > div { display:flex; gap:10px; flex-wrap:wrap; align-items:baseline; }
.d1-plus-trinket-choices { opacity:.92; }
'''
        write(rel, s)
    print("Applied shared Trinket Catalyst scout")
    raise SystemExit(0)

# ============================= BETA-3 overlay =============================
# Builder.findFreeSpace global fix.
rel = "crates/seedfinder-core/src/builder.rs"; s = read(rel)
if "SHPD-BETA3-BUILDER" not in s:
    pattern = r"fn free_space_from_collisions\(\n.*?\n\}\n\n/// Exact float/double operation ordering of `Builder\.angleBetweenPoints`\."
    replacement = '''/// SHPD-BETA3-BUILDER
fn free_space_from_collisions(
    start: Point,
    colliding: &mut [Rect],
    mut space: Rect,
    rng: &mut RandomStack,
) -> Rect {
    let mut count = colliding.len();
    loop {
        let mut kept = 0_usize;
        let mut closest_room = None;
        let mut closest_distance_sq = i64::MAX;
        for index in 0..count {
            let bounds = colliding[index];
            let intersects = space.left.max(bounds.left) < space.right.min(bounds.right)
                && space.top.max(bounds.top) < space.bottom.min(bounds.bottom);
            if !intersects { continue; }
            colliding[kept] = bounds;
            let mut dx = 0_i32;
            let mut dy = 0_i32;
            let mut inside = true;
            if start.x <= bounds.left { inside = false; dx = bounds.left.wrapping_sub(start.x); }
            else if start.x >= bounds.right { inside = false; dx = start.x.wrapping_sub(bounds.right); }
            if start.y <= bounds.top { inside = false; dy = bounds.top.wrapping_sub(start.y); }
            else if start.y >= bounds.bottom { inside = false; dy = start.y.wrapping_sub(bounds.bottom); }
            if inside { space.set(start.x, start.y, start.x, start.y); return space; }
            let d2 = i64::from(dx)*i64::from(dx) + i64::from(dy)*i64::from(dy);
            if d2 < closest_distance_sq { closest_distance_sq = d2; closest_room = Some(kept); }
            kept += 1;
        }
        count = kept;
        if let Some(closest) = closest_room {
            let bounds = colliding[closest];
            let mut wd = i32::MAX;
            if bounds.left >= start.x { wd = space.right.wrapping_sub(bounds.left).wrapping_mul(space.height().wrapping_add(1)); }
            else if bounds.right <= start.x { wd = bounds.right.wrapping_sub(space.left).wrapping_mul(space.height().wrapping_add(1)); }
            let mut hd = i32::MAX;
            if bounds.top >= start.y { hd = space.bottom.wrapping_sub(bounds.top).wrapping_mul(space.width().wrapping_add(1)); }
            else if bounds.bottom <= start.y { hd = bounds.bottom.wrapping_sub(space.top).wrapping_mul(space.width().wrapping_add(1)); }
            let reduce_width = wd < hd || (wd == hd && rng.int_bound(2) == 0);
            if reduce_width {
                if bounds.left >= start.x && bounds.left < space.right { space.right = bounds.left; }
                if bounds.right <= start.x && bounds.right > space.left { space.left = bounds.right; }
            } else {
                if bounds.top >= start.y && bounds.top < space.bottom { space.bottom = bounds.top; }
                if bounds.bottom <= start.y && bounds.bottom > space.top { space.top = bounds.bottom; }
            }
            colliding.copy_within(closest + 1..count, closest); count -= 1;
        } else { count = 0; }
        if count == 0 { return space; }
    }
}

/// Exact float/double operation ordering of `Builder.angleBetweenPoints`.'''
    s = regex_once(s, pattern, replacement, "BETA Builder.findFreeSpace")
    write(rel, s)

# Generator artifact exhaustion fallback.
rel = "crates/seedfinder-core/src/generator.rs"; s = read(rel)
if "SHPD-BETA3-GENERATOR" not in s:
    old = '''    if let Some(artifact) = random_artifact(random, generator)? {
        Ok(GeneratedItem::Artifact(artifact))
    } else {
        let index = select_seeded_identity_index(random, generator, GeneratorCategory::Ring)?;
        randomize_identity(random, GeneratorCategory::Ring, index, true)
    }
'''
    new = '''    // SHPD-BETA3-GENERATOR
    if let Some(artifact) = random_artifact(random, generator)? {
        Ok(GeneratedItem::Artifact(artifact))
    } else {
        let index = select_default_identity_index(random, GeneratorCategory::Ring)?;
        randomize_identity(random, GeneratorCategory::Ring, index, false)
    }
'''
    s = once(s, old, new, "BETA artifact fallback")
    write(rel, s)

# Quest-room graph geometry changes.
rel = "crates/seedfinder-core/src/room.rs"; s = read(rel)
if "SHPD-BETA3-QUEST-GEOMETRY" not in s:
    s = once(s, "                QuestRoomKind::MassGrave => 7,\n",
             "                // SHPD-BETA3-QUEST-GEOMETRY\n                QuestRoomKind::MassGrave => 11,\n", "MassGrave min width")
    s = once(s, '''                QuestRoomKind::Blacksmith => self
                    .size_category
                    .expect("BlacksmithRoom has a size category")
                    .min_dimension()
                    .max(6),
''', '''                QuestRoomKind::Blacksmith => self
                    .size_category
                    .expect("BlacksmithRoom has a size category")
                    .min_dimension()
                    .max(8),
''', "Blacksmith min size")
    s = once(s, "                QuestRoomKind::MassGrave | QuestRoomKind::RotGarden => 10,\n",
             "                QuestRoomKind::MassGrave => 11,\n                QuestRoomKind::RotGarden => 10,\n", "MassGrave max width")
    s = once(s, '''    pub fn min_height(&self) -> i32 {
        // All graph-relevant v3.3.8 overrides are symmetric.
        self.min_width()
    }

    #[must_use]
    pub fn max_height(&self) -> i32 {
        self.max_width()
    }
''', '''    pub fn min_height(&self) -> i32 {
        if matches!(self.kind, RoomKind::Quest(QuestRoomKind::MassGrave)) { 10 } else { self.min_width() }
    }

    #[must_use]
    pub fn max_height(&self) -> i32 {
        if matches!(self.kind, RoomKind::Quest(QuestRoomKind::MassGrave)) { 10 } else { self.max_width() }
    }
''', "MassGrave asymmetric height")
    anchor = '''        match self.kind {
            RoomKind::Standard(StandardRoomKind::SewerPipe)
'''
    repl = '''        match self.kind {
            RoomKind::Quest(QuestRoomKind::MassGrave) => {
                point.y == self.bounds.bottom && (point.x - (self.bounds.left + self.bounds.right) / 2).abs() <= 2
            }
            RoomKind::Quest(QuestRoomKind::Blacksmith) => {
                if point.y == self.bounds.top { point.x == self.bounds.left + 1 || point.x == self.bounds.right - 1 }
                else if point.y == self.bounds.top + 1 { false } else { true }
            }
            RoomKind::Standard(StandardRoomKind::SewerPipe)
'''
    s = once(s, anchor, repl, "beta quest canConnect points")
    write(rel, s)

# Hallway transition room no longer consumes random center-deco draw.
rel = "crates/seedfinder-core/src/city_rooms.rs"; s = read(rel)
if "SHPD-BETA3-HALLWAY" not in s:
    old = '''        level.map.set(
            connection_space.left + 1,
            connection_space.top + 1,
            if rng.int_bound(2) == 0 {
                terrain::STATUE_SP
            } else {
                terrain::REGION_DECO_ALT
            },
        );
'''
    new = '''        // SHPD-BETA3-HALLWAY
        level.map.set(
            connection_space.left + 1,
            connection_space.top + 1,
            if rooms[room].is_entrance() { terrain::ENTRANCE }
            else if rooms[room].is_exit() { terrain::EXIT }
            else if rng.int_bound(2) == 0 { terrain::STATUE_SP }
            else { terrain::REGION_DECO_ALT },
        );
'''
    s = once(s, old, new, "beta Hallway center")
    s = once(s, "                            terrain::STATUE_SP | terrain::REGION_DECO_ALT\n",
             "                            terrain::STATUE_SP | terrain::REGION_DECO_ALT | terrain::ENTRANCE | terrain::EXIT\n",
             "beta Hallway transition lookup")
    write(rel, s)

# CavesPainter does not erode BlacksmithRoom corners in beta.
rel = "crates/seedfinder-core/src/caves_rooms.rs"; s = read(rel)
if "SHPD-BETA3-CAVES-DECORATE" not in s:
    old = '''        if !rooms[room].is_standard() || rooms[room].width() <= 4 || rooms[room].height() <= 4 {
            continue;
        }
'''
    new = '''        // SHPD-BETA3-CAVES-DECORATE
        if !rooms[room].is_standard()
            || matches!(rooms[room].kind, RoomKind::Quest(crate::room::QuestRoomKind::Blacksmith))
            || rooms[room].width() <= 4 || rooms[room].height() <= 4 {
            continue;
        }
'''
    s = once(s, old, new, "Caves Blacksmith decorator skip")
    write(rel, s)

# New Imp/Vault quest eagerly rolls reward options during City initRooms.
rel = "crates/seedfinder-core/src/quests.rs"; s = read(rel)
if "SHPD-BETA3-IMP" not in s:
    # Import random_artifact if not already present.
    s = s.replace("random_armor, random_category,", "random_armor, random_artifact, random_category,", 1)
    old = '''        let depth = self.depth.expect("scheduled Imp quest records its depth");
        self.target = Some(match depth {
            18 if random.int_bound(2) != 0 => ImpTarget::Golem,
            19 => ImpTarget::Golem,
            _ => ImpTarget::Monk,
        });
        self.given = false;
        let (reward, rejected) = generate_imp_reward(random, generator, depth)?;
        self.reward = Some(reward);
        self.rejected_cursed_rings = rejected;
        Ok(())
'''
    new = '''        let depth = self.depth.expect("scheduled Imp quest records its depth");
        // SHPD-BETA3-IMP
        self.target = None;
        self.given = false;
        self.reward = None;
        self.rejected_cursed_rings = 0;
        consume_beta3_imp_reward_generation(random, generator, depth)?;
        Ok(())
'''
    s = once(s, old, new, "beta Imp finish schedule")
    idx = s.find("/// All quest state reset by `Dungeon.init()`.")
    if idx < 0: raise RuntimeError("Could not find QuestState insertion point")
    helper = '''/// SHPD-BETA3-IMP
fn consume_beta3_imp_reward_generation(
    random: &mut RandomStack,
    generator: &mut GeneratorState,
    depth: u8,
) -> Result<(), QuestError> {
    let first_ring_kind = if random_artifact(random, generator)?.is_some() {
        None
    } else {
        let GeneratedItem::Ring(ring) = random_category(random, generator, GeneratorCategory::Ring, i32::from(depth))? else { unreachable!() };
        random.int_range(2, 4);
        Some(ring.kind)
    };
    loop {
        let GeneratedItem::Ring(ring) = random_category(random, generator, GeneratorCategory::Ring, i32::from(depth))? else { unreachable!() };
        if first_ring_kind != Some(ring.kind) { break; }
    }
    random.int_range(2, 4);
    if random.int_bound(2) == 0 {
        let _ = random_category(random, generator, GeneratorCategory::WeaponTier5, i32::from(depth))?;
        let _ = random_weapon_enchantment(random); random.int_range(2, 4);
        let _ = random_category(random, generator, GeneratorCategory::MissileTier4, i32::from(depth))?;
        let _ = random_weapon_enchantment(random); random.int_range(3, 5);
    } else {
        let _ = random_category(random, generator, GeneratorCategory::MissileTier5, i32::from(depth))?;
        let _ = random_weapon_enchantment(random); random.int_range(2, 4);
        let _ = random_category(random, generator, GeneratorCategory::WeaponTier4, i32::from(depth))?;
        let _ = random_weapon_enchantment(random); random.int_range(3, 5);
    }
    let _ = random_armor_glyph(random); random.int_range(2, 4);
    let _ = random_category(random, generator, GeneratorCategory::Wand, i32::from(depth))?;
    random.int_range(2, 4);
    Ok(())
}

'''
    s = s[:idx] + helper + s[idx:]
    write(rel, s)

print("Applied Shattered PD v4.0.0-BETA-3 deterministic overlay")
