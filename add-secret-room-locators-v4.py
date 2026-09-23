#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else "app")

p=root/"crates/seedfinder-core/src/level_map/mod.rs"
s=p.read_text()
old='''    /// Secret-room class names in the same order as secret_rooms.
    pub secret_room_kinds: Vec<String>,
    pub traps: Vec<MapTrap>,
'''
new='''    /// Secret-room class names in the same order as secret_rooms.
    pub secret_room_kinds: Vec<String>,
    /// Actionable locator data in the same order as secret_rooms.
    pub secret_room_locators: Vec<SecretRoomLocator>,
    pub traps: Vec<MapTrap>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
#[cfg_attr(feature = "json-query", derive(serde::Serialize))]
#[cfg_attr(feature = "json-query", serde(rename_all = "camelCase"))]
pub struct SecretRoomLocator {
    pub via: Option<String>,
    pub from: String,
    pub doors: usize,
    pub water: bool,
    pub pit: bool,
    pub wall: &'static str,
}
'''
if new not in s:
    if old not in s: raise SystemExit("locator struct anchor changed")
    s=s.replace(old,new,1)

# helpers before snapshot
anchor='''#[allow(clippy::too_many_arguments)]
fn snapshot(
'''
helpers=r'''fn locator_room_label(room: &Room) -> String {
    match room.kind {
        RoomKind::Entrance(_) => "Entrance".to_owned(),
        RoomKind::Exit(_) => "Stairs".to_owned(),
        RoomKind::Standard(_) => "Standard Room".to_owned(),
        RoomKind::Connection(crate::room::ConnectionRoomKind::Maze) => "Maze".to_owned(),
        RoomKind::Connection(_) => "Connection Room".to_owned(),
        RoomKind::Special(kind) => format!("{kind:?}"),
        RoomKind::Quest(kind) => format!("{kind:?}"),
        RoomKind::Secret(kind) => format!("{kind:?}"),
    }
}

fn locator_features(room: &Room, level: &Level) -> (bool, bool) {
    let mut water = false;
    let mut pit = false;
    for y in room.bounds.top + 1..room.bounds.bottom {
        for x in room.bounds.left + 1..room.bounds.right {
            let cell = level.map.cell(x, y);
            let flags = crate::geometry::terrain::flags(level.map.cells[cell]);
            water |= flags & crate::geometry::terrain::LIQUID != 0;
            pit |= flags & crate::geometry::terrain::PIT != 0;
        }
    }
    (water, pit)
}

fn locator_wall(room: &Room, point: crate::geometry::Point) -> &'static str {
    if point.y == room.bounds.top { "N" }
    else if point.y == room.bounds.bottom { "S" }
    else if point.x == room.bounds.left { "W" }
    else if point.x == room.bounds.right { "E" }
    else { "?" }
}

fn secret_room_locators(rooms: &[Room], level: &Level) -> Vec<SecretRoomLocator> {
    let mut out = Vec::new();
    for (secret_id, secret) in rooms.iter().enumerate() {
        if !secret.is_secret() { continue; }
        let Some(first_link) = secret.connected.first() else { continue; };
        let first_id = first_link.room;
        let first = &rooms[first_id];

        // One nested secret/maze maximum: describe the door the player can
        // actually search for, then name the intermediate room as "via".
        let nested = first.is_secret()
            || matches!(first.kind, RoomKind::Connection(crate::room::ConnectionRoomKind::Maze));
        let (via, origin_id, door) = if nested {
            let Some(link) = first.connected.iter()
                .find(|link| link.room != secret_id && !rooms[link.room].is_secret()) else { continue; };
            let origin_id = link.room;
            let origin = &rooms[origin_id];
            let door = link.door.or_else(|| origin.connected.iter()
                .find(|reverse| reverse.room == first_id).and_then(|reverse| reverse.door));
            (Some(locator_room_label(first)), origin_id, door)
        } else {
            let origin_id = first_id;
            let origin = &rooms[origin_id];
            let door = first_link.door.or_else(|| origin.connected.iter()
                .find(|reverse| reverse.room == secret_id).and_then(|reverse| reverse.door));
            (None, origin_id, door)
        };
        let origin = &rooms[origin_id];
        let doors = origin.connected.iter()
            .filter(|link| !rooms[link.room].is_secret())
            .count();
        let (water, pit) = locator_features(origin, level);
        out.push(SecretRoomLocator {
            via,
            from: locator_room_label(origin),
            doors,
            water,
            pit,
            wall: door.map_or("?", |door| locator_wall(origin, door.point)),
        });
    }
    out
}

'''
if "fn secret_room_locators(" not in s:
    if anchor not in s: raise SystemExit("snapshot anchor changed")
    s=s.replace(anchor,helpers+anchor,1)

old='''        secret_room_kinds: rooms
            .iter()
            .filter_map(|room| match room.kind {
                RoomKind::Secret(kind) => Some(format!("{kind:?}")),
                _ => None,
            })
            .collect(),
        traps: level
'''
new='''        secret_room_kinds: rooms
            .iter()
            .filter_map(|room| match room.kind {
                RoomKind::Secret(kind) => Some(format!("{kind:?}")),
                _ => None,
            })
            .collect(),
        secret_room_locators: secret_room_locators(rooms, level),
        traps: level
'''
if new not in s:
    if old not in s: raise SystemExit("snapshot locator anchor changed")
    s=s.replace(old,new,1)
p.write_text(s)

p=root/"crates/seedfinder-core/src/level_map/json.rs"
s=p.read_text()
old='''        "secretRoomKinds": map.secret_room_kinds,
        "secretDoors":'''
new='''        "secretRoomKinds": map.secret_room_kinds,
        "secretRoomLocators": map.secret_room_locators,
        "secretDoors":'''
if new not in s:
    if old not in s: raise SystemExit("JSON locator anchor changed")
    s=s.replace(old,new,1)
p.write_text(s)

p=root/"web/src/lib/level-map/types.ts"
s=p.read_text()
old='''  secretRoomKinds?: string[];
  secretDoors: number[];
'''
new='''  secretRoomKinds?: string[];
  secretRoomLocators?: {
    via?: string | null;
    from: string;
    doors: number;
    water: boolean;
    pit: boolean;
    wall: "N" | "S" | "E" | "W" | "?";
  }[];
  secretDoors: number[];
'''
if new not in s:
    if old not in s: raise SystemExit("TS locator anchor changed")
    s=s.replace(old,new,1)
p.write_text(s)

p=root/"web/src/designs/one/ScoutPanel.tsx"
s=p.read_text()
old='''          const rawKind = map.secretRoomKinds?.[index] ?? "Secret room";
          const kind = rawKind.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
          return kind + " · " + doors.length + " " +
            (doors.length === 1 ? "door" : "doors") + " · " + wall;
'''
new='''          const rawKind = map.secretRoomKinds?.[index] ?? "Secret room";
          const kind = rawKind.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
          const locator = map.secretRoomLocators?.[index];
          if (!locator) {
            return kind + " · " + doors.length + " " +
              (doors.length === 1 ? "door" : "doors") + " · " + wall;
          }
          return [
            kind,
            locator.via ? "via " + locator.via : null,
            "from " + locator.from,
            locator.doors + " " + (locator.doors === 1 ? "door" : "doors"),
            locator.water ? "water" : null,
            locator.pit ? "pit" : null,
            locator.wall,
          ].filter(Boolean).join(" · ");
'''
if old not in s: raise SystemExit("Scout named summary anchor changed")
s=s.replace(old,new,1)
p.write_text(s)
print("Added full secret-room locator detail")
