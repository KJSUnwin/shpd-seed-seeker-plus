#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else "app")

# Expose secret room kinds in the authoritative v4 map document.
p=root/"crates/seedfinder-core/src/level_map/mod.rs"
s=p.read_text()
old='''    /// Inclusive [left, top, right, bottom] room bounds.
    pub secret_rooms: Vec<[i32; 4]>,
    pub traps: Vec<MapTrap>,
'''
new='''    /// Inclusive [left, top, right, bottom] room bounds.
    pub secret_rooms: Vec<[i32; 4]>,
    /// Secret-room class names in the same order as secret_rooms.
    pub secret_room_kinds: Vec<String>,
    pub traps: Vec<MapTrap>,
'''
if new not in s:
    if old not in s: raise SystemExit("LevelMap fields changed")
    s=s.replace(old,new,1)
old='''        secret_rooms: rooms
            .iter()
            .filter(|room| matches!(room.kind, RoomKind::Secret(_)))
            .map(|room| {
                [
                    room.bounds.left,
                    room.bounds.top,
                    room.bounds.right,
                    room.bounds.bottom,
                ]
            })
            .collect(),
        traps: level
'''
new='''        secret_rooms: rooms
            .iter()
            .filter(|room| matches!(room.kind, RoomKind::Secret(_)))
            .map(|room| {
                [
                    room.bounds.left,
                    room.bounds.top,
                    room.bounds.right,
                    room.bounds.bottom,
                ]
            })
            .collect(),
        secret_room_kinds: rooms
            .iter()
            .filter_map(|room| match room.kind {
                RoomKind::Secret(kind) => Some(format!("{kind:?}")),
                _ => None,
            })
            .collect(),
        traps: level
'''
if new not in s:
    if old not in s: raise SystemExit("snapshot secret rooms changed")
    s=s.replace(old,new,1)
p.write_text(s)

p=root/"crates/seedfinder-core/src/level_map/json.rs"
s=p.read_text()
old='''        "secretRooms": map.secret_rooms,
        "secretDoors": map.terrain.iter().enumerate()'''
new='''        "secretRooms": map.secret_rooms,
        "secretRoomKinds": map.secret_room_kinds,
        "secretDoors": map.terrain.iter().enumerate()'''
if new not in s:
    if old not in s: raise SystemExit("map json changed")
    s=s.replace(old,new,1)
p.write_text(s)

p=root/"web/src/lib/level-map/types.ts"
s=p.read_text()
old='''  secretRooms: Rectangle[];
  secretDoors: number[];
'''
new='''  secretRooms: Rectangle[];
  /** Secret-room class names, index-aligned with secretRooms. */
  secretRoomKinds?: string[];
  secretDoors: number[];
'''
if new not in s:
    if old not in s: raise SystemExit("map TS type changed")
    s=s.replace(old,new,1)
p.write_text(s)

# Put the room kind in the already-live floor-card summary.
p=root/"web/src/designs/one/ScoutPanel.tsx"
s=p.read_text()
old='''          return "Secret room " + (index + 1) + " · " + doors.length + " " +
            (doors.length === 1 ? "door" : "doors") + " · " + wall;
'''
new='''          const rawKind = map.secretRoomKinds?.[index] ?? "Secret room";
          const kind = rawKind.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
          return kind + " · " + doors.length + " " +
            (doors.length === 1 ? "door" : "doors") + " · " + wall;
'''
if old not in s: raise SystemExit("Scout summary text changed")
s=s.replace(old,new,1)
p.write_text(s)

print("Added v4 secret-room type names")
