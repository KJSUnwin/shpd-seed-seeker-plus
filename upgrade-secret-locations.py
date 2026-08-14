#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: upgrade-nested-secret-locator.py PATH_TO_UPSTREAM_APP")

root = Path(sys.argv[1]).resolve()
MARKER = "SHPD-NESTED-SECRET-LOCATOR-V2.6"

def read(rel):
    return (root / rel).read_text(encoding="utf-8")

def write(rel, text):
    (root / rel).write_text(text, encoding="utf-8")

def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Could not find {label}. Run upgrade-secret-locations.py first.")
    return text.replace(old, new, 1)

rel = "crates/seedfinder-core/src/main_world.rs"
s = read(rel)

if MARKER not in s:
    s = replace_once(
        s,
        "use crate::room::{Room, RoomKind, SecretRoomKind};\n",
        "use crate::room::{ConnectionRoomKind, Room, RoomKind, SecretRoomKind};\n",
        "ConnectionRoomKind import",
    )

    s = replace_once(
        s,
        '''pub struct ScoutSecretRoomMetadata {
    pub kind: SecretRoomKind,
    pub adjoining_room: String,
    pub visible_doors: usize,
''',
        '''pub struct ScoutSecretRoomMetadata {
    pub kind: SecretRoomKind,
    pub via_room: Option<String>,
    pub adjoining_room: String,
    pub visible_doors: usize,
''',
        "ScoutSecretRoomMetadata via field",
    )

    old_fn = r'''fn scout_secret_rooms(rooms: &[Room], level: &Level) -> Vec<ScoutSecretRoomMetadata> {
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

    new_fn = r'''/// SHPD-NESTED-SECRET-LOCATOR-V2.6
fn scout_via_label(kind: RoomKind) -> String {
    match kind {
        RoomKind::Secret(kind) => format!("{kind:?}"),
        RoomKind::Connection(kind) => format!("{kind:?}"),
        _ => scout_room_label(kind),
    }
}

fn scout_secret_rooms(rooms: &[Room], level: &Level) -> Vec<ScoutSecretRoomMetadata> {
    let mut output = Vec::new();

    for (secret_id, secret_room) in rooms.iter().enumerate() {
        let RoomKind::Secret(kind) = secret_room.kind else {
            continue;
        };

        let Some(target_connection) = secret_room.connected.first() else {
            continue;
        };

        let first_id = target_connection.room;
        let first = &rooms[first_id];

        let nested = first.is_secret()
            || matches!(first.kind, RoomKind::Connection(ConnectionRoomKind::Maze));

        let (via_room, visible_id, entrance_door) = if nested {
            let Some(from_via) = first.connected.iter().find(|candidate| {
                candidate.room != secret_id && !rooms[candidate.room].is_secret()
            }) else {
                continue;
            };

            let visible_id = from_via.room;
            let visible = &rooms[visible_id];
            let door = from_via.door.or_else(|| {
                visible
                    .connected
                    .iter()
                    .find(|reverse| reverse.room == first_id)
                    .and_then(|reverse| reverse.door)
            });

            (Some(scout_via_label(first.kind)), visible_id, door)
        } else {
            let visible_id = first_id;
            let visible = &rooms[visible_id];
            let door = target_connection.door.or_else(|| {
                visible
                    .connected
                    .iter()
                    .find(|reverse| reverse.room == secret_id)
                    .and_then(|reverse| reverse.door)
            });

            (None, visible_id, door)
        };

        let visible = &rooms[visible_id];

        let visible_doors = visible
            .connected
            .iter()
            .filter(|candidate| {
                !rooms[candidate.room].is_secret()
                    && (!nested || candidate.room != first_id)
            })
            .count();

        let (contains_water, contains_pit) = scout_room_features(visible, level);

        output.push(ScoutSecretRoomMetadata {
            kind,
            via_room,
            adjoining_room: scout_room_label(visible.kind),
            visible_doors,
            contains_water,
            contains_pit,
            wall: entrance_door.map_or("?", |door| scout_secret_wall(visible, door.point)),
        });
    }

    output
}
'''
    s = replace_once(s, old_fn, new_fn, "nested-aware scout_secret_rooms")
    write(rel, s)

rel = "crates/seedfinder-wasm/src/lib.rs"
s = read(rel)

if MARKER not in s:
    s = replace_once(
        s,
        '''struct ScoutSecretRoomOutput {
    kind: &'static str,
    room: String,
''',
        '''struct ScoutSecretRoomOutput {
    kind: &'static str,
    via_room: Option<String>,
    room: String,
''',
        "ScoutSecretRoomOutput via field",
    )

    s = replace_once(
        s,
        '''                .map(|secret| ScoutSecretRoomOutput {
                    kind: scout_secret_room_name(secret.kind),
                    room: secret.adjoining_room,
''',
        '''                .map(|secret| ScoutSecretRoomOutput {
                    kind: scout_secret_room_name(secret.kind),
                    via_room: secret.via_room,
                    room: secret.adjoining_room,
''',
        "WASM via mapping",
    )
    write(rel, s)

rel = "web/src/lib/wasm/types.ts"
s = read(rel)

if MARKER not in s:
    s = replace_once(
        s,
        '''export interface ScoutSecretRoom {
  kind: SecretRoomName
  room: string
''',
        '''export interface ScoutSecretRoom {
  kind: SecretRoomName
  viaRoom?: string | null
  room: string
''',
        "ScoutSecretRoom viaRoom type",
    )
    write(rel, s)

rel = "web/src/designs/one/ScoutPanel.tsx"
s = read(rel)

if MARKER not in s:
    old_summary = r'''const secretRoomSummary = (secret: ScoutSecretRoom) => {
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
    new_summary = r'''// SHPD-NESTED-SECRET-LOCATOR-V2.6
const secretRoomSummary = (secret: ScoutSecretRoom) => {
  const parts = [
    secretRoomLabel(secret.kind),
    secret.viaRoom ? `via ${prettyScoutToken(secret.viaRoom)}` : null,
    `from ${prettyScoutToken(secret.room)}`,
    `${secret.doors} ${secret.doors === 1 ? 'door' : 'doors'}`,
    secret.water ? 'water' : null,
    secret.pit ? 'pit' : null,
    secret.wall,
  ]
  return parts.filter((part): part is string => Boolean(part)).join(' · ')
}
'''
    s = replace_once(s, old_summary, new_summary, "nested secret summary")
    write(rel, s)

print("Seed Seeker Plus V2.6 nested-secret locator applied successfully.")
