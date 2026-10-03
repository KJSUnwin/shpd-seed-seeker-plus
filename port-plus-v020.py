#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else "app")

def replace(path, old, new, label):
    p=root/path; s=p.read_text()
    if new in s: return
    if old not in s: raise SystemExit(f"{label} anchor changed")
    p.write_text(s.replace(old,new,1))

# Core: add ordered, actionable secret-room metadata to each generated map.
replace("crates/seedfinder-core/src/level_map/mod.rs",
'''    /// Inclusive [left, top, right, bottom] room bounds.
    pub secret_rooms: Vec<[i32; 4]>,
    pub traps: Vec<MapTrap>,
''',
'''    /// Inclusive [left, top, right, bottom] room bounds.
    pub secret_rooms: Vec<[i32; 4]>,
    pub secret_room_info: Vec<SecretRoomInfo>,
    pub traps: Vec<MapTrap>,
''',"LevelMap secret field")

replace("crates/seedfinder-core/src/level_map/mod.rs",
'''/// Selects the branch's terrain atlas; both quest branches use game branch 1.
''',
'''#[derive(Clone, Debug, Eq, PartialEq)]
#[cfg_attr(feature = "json-query", derive(serde::Serialize))]
#[cfg_attr(feature = "json-query", serde(rename_all = "camelCase"))]
pub struct SecretRoomInfo {
    pub kind: String,
    pub via: Option<String>,
    pub from: String,
    pub doors: usize,
    pub water: bool,
    pub pit: bool,
    pub wall: &'static str,
}

fn plus_room_label(room: &Room) -> String {
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
fn plus_features(room: &Room, level: &Level) -> (bool, bool) {
    let mut water=false; let mut pit=false;
    for y in room.bounds.top+1..room.bounds.bottom {
        for x in room.bounds.left+1..room.bounds.right {
            let cell=level.map.cell(x,y);
            let flags=crate::geometry::terrain::flags(level.map.cells[cell]);
            water |= flags & crate::geometry::terrain::LIQUID != 0;
            pit |= flags & crate::geometry::terrain::PIT != 0;
        }
    }
    (water,pit)
}
fn plus_wall(room:&Room, p:crate::geometry::Point)->&'static str {
    if p.y==room.bounds.top {"N"} else if p.y==room.bounds.bottom {"S"}
    else if p.x==room.bounds.left {"W"} else if p.x==room.bounds.right {"E"} else {"?"}
}
fn plus_secret_info(rooms:&[Room], level:&Level)->Vec<SecretRoomInfo> {
    let mut out=Vec::new();
    for (sid,secret) in rooms.iter().enumerate() {
        let RoomKind::Secret(kind)=secret.kind else {continue};
        if matches!(kind, crate::room::SecretRoomKind::Mine | crate::room::SecretRoomKind::RatKing) {continue}
        let Some(link)=secret.connected.first() else {continue};
        let first_id=link.room; let first=&rooms[first_id];
        let nested=first.is_secret() || matches!(first.kind,RoomKind::Connection(crate::room::ConnectionRoomKind::Maze));
        let (via,oid,door)=if nested {
            let Some(next)=first.connected.iter().find(|x| x.room!=sid && !rooms[x.room].is_secret()) else {continue};
            let oid=next.room; let origin=&rooms[oid];
            let door=next.door.or_else(||origin.connected.iter().find(|x|x.room==first_id).and_then(|x|x.door));
            (Some(plus_room_label(first)),oid,door)
        } else {
            let oid=first_id; let origin=&rooms[oid];
            let door=link.door.or_else(||origin.connected.iter().find(|x|x.room==sid).and_then(|x|x.door));
            (None,oid,door)
        };
        let origin=&rooms[oid];
        let doors=origin.connected.iter().filter(|x|!rooms[x.room].is_secret() && (!nested || x.room!=first_id)).count();
        let (water,pit)=plus_features(origin,level);
        out.push(SecretRoomInfo{kind:format!("{kind:?}"),via,from:plus_room_label(origin),doors,water,pit,wall:door.map_or("?",|d|plus_wall(origin,d.point))});
    }
    out
}

/// Selects the branch's terrain atlas; both quest branches use game branch 1.
''',"SecretRoomInfo helpers")

replace("crates/seedfinder-core/src/level_map/mod.rs",
'''            .collect(),
        traps: level
''',
'''            .collect(),
        secret_room_info: plus_secret_info(rooms, level),
        traps: level
''',"snapshot secret info")

replace("crates/seedfinder-core/src/level_map/json.rs",
'''        "secretRooms": map.secret_rooms,
        "secretDoors":''',
'''        "secretRooms": map.secret_rooms,
        "secretRoomInfo": map.secret_room_info,
        "secretDoors":''',"map JSON secret info")

replace("web/src/features/level-map/types.ts",
'''  secretRooms: Rectangle[];
  secretDoors: number[];
''',
'''  secretRooms: Rectangle[];
  secretRoomInfo?: {
    kind: string;
    via?: string | null;
    from: string;
    doors: number;
    water: boolean;
    pit: boolean;
    wall: "N" | "S" | "E" | "W" | "?";
  }[];
  secretDoors: number[];
''',"web map secret type")

# Scout UI: load map metadata and show it without opening Map.
p=root/"web/src/features/scout/ScoutPanel.tsx"; s=p.read_text()
anchor='''  const [openMap, setOpenMap] = useState<{ seed: string; depth: number } | undefined>(undefined);
'''
if "secretSummaries" not in s:
    s=s.replace(anchor,anchor+'''  const [secretSummaries, setSecretSummaries] = useState<Record<number, string[]>>({});
''',1)
needle='''  }, [result]);

  // `?? []` guards against cached worker responses from before quests existed.
'''
effect='''  }, [result]);

  useEffect(() => {
    let active = true;
    setSecretSummaries({});
    if (!result) return () => { active = false; };
    for (const [depth] of floors) {
      if (!isMapDepthSupported(depth)) continue;
      void requestLevelMap({
        seed: result.seed.code,
        depth,
        challenges: renderedChallenges,
        selectedTrinket: result.selectedTrinket,
      }).then(({ map }) => {
        if (!active || !map.secretRoomInfo?.length) return;
        const pretty = (v: string) => v.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ");
        const lines = map.secretRoomInfo.map((x) =>
          [
            pretty(x.kind),
            x.via ? "via " + pretty(x.via) : null,
            "from " + pretty(x.from),
            x.doors + " " + (x.doors === 1 ? "door" : "doors"),
            x.water ? "water" : null,
            x.pit ? "pit" : null,
            x.wall,
          ].filter(Boolean).join(" · ")
        );
        setSecretSummaries((current) => ({ ...current, [depth]: lines }));
      }).catch(() => undefined);
    }
    return () => { active = false; };
  }, [result?.seed.code, result?.selectedTrinket, renderedChallenges, floors]);

  // `?? []` guards against cached worker responses from before quests existed.
'''
if "setSecretSummaries({});" not in s:
    if needle not in s: raise SystemExit("Scout floors effect anchor changed")
    s=s.replace(needle,effect,1)
render='''                <div
                  id={`scout-floor-map-${depth}`}
'''
summary='''                {(secretSummaries[depth]?.length ?? 0) > 0 && (
                  <div className="d1-plus-floor-secret-summary">
                    {secretSummaries[depth].map((line) => <div key={line}>{line}</div>)}
                  </div>
                )}
                <div
                  id={`scout-floor-map-${depth}`}
'''
if "d1-plus-floor-secret-summary" not in s:
    if render not in s: raise SystemExit("Scout floor render anchor changed")
    s=s.replace(render,summary,1)
p.write_text(s)

p=root/"web/src/features/scout/floor-map-inline.css"; css=p.read_text()
if "Seed Seeker Plus secret summary" not in css:
    css+='''\n/* Seed Seeker Plus secret summary */\n.d1-plus-floor-secret-summary{margin:5px 12px 7px;padding:5px 8px;border-radius:6px;font-size:12px;font-weight:650;line-height:1.4;background:color-mix(in srgb,var(--region) 9%,transparent);border:1px solid color-mix(in srgb,var(--region) 28%,transparent)}\n'''
    p.write_text(css)
print("Applied v0.20.8 Plus secret-room summaries")
