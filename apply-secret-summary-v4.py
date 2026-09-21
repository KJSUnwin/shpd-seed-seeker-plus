#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else "app")
p=root/"web/src/designs/one/ScoutPanel.tsx"
s=p.read_text()
s=s.replace(
'import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";',
'import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";'
)
anchor='''  const [openMap, setOpenMap] = useState<{ seed: string; depth: number } | undefined>(undefined);
'''
insert=anchor+'''  const [secretSummaries, setSecretSummaries] = useState<Record<number, string[]>>({});
'''
if "secretSummaries" not in s:
    if anchor not in s: raise SystemExit("state anchor changed")
    s=s.replace(anchor,insert,1)
anchor2='''  useEffect(() => setOpenMap(undefined), [result?.seed.code]);
'''
insert2=anchor2+'''  useEffect(() => {
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
        if (!active || map.secretRooms.length === 0) return;
        const lines = map.secretRooms.map((room, index) => {
          const [left, top, right, bottom] = room;
          const doors = map.secretDoors.filter((cell) => {
            const x = cell % map.width;
            const y = Math.floor(cell / map.width);
            return x >= left && x <= right && y >= top && y <= bottom;
          });
          const door = doors[0];
          let wall = "?";
          if (door !== undefined) {
            const x = door % map.width;
            const y = Math.floor(door / map.width);
            wall = y === top ? "N" : y === bottom ? "S" : x === left ? "W" : x === right ? "E" : "?";
          }
          return "Secret room " + (index + 1) + " · " + doors.length + " " +
            (doors.length === 1 ? "door" : "doors") + " · " + wall;
        });
        setSecretSummaries((current) => ({ ...current, [depth]: lines }));
      }).catch(() => undefined);
    }
    return () => { active = false; };
  }, [result?.seed.code, result?.selectedTrinket, renderedChallenges]);
'''
# floors declared later than this effect => cannot use. Place effect after floors useMemo.
if "setSecretSummaries({});" not in s:
    pass
# instead locate end of floors useMemo
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
        if (!active || map.secretRooms.length === 0) return;
        const lines = map.secretRooms.map((room, index) => {
          const [left, top, right, bottom] = room;
          const doors = map.secretDoors.filter((cell) => {
            const x = cell % map.width;
            const y = Math.floor(cell / map.width);
            return x >= left && x <= right && y >= top && y <= bottom;
          });
          const door = doors[0];
          let wall = "?";
          if (door !== undefined) {
            const x = door % map.width;
            const y = Math.floor(door / map.width);
            wall = y === top ? "N" : y === bottom ? "S" : x === left ? "W" : x === right ? "E" : "?";
          }
          return "Secret room " + (index + 1) + " · " + doors.length + " " +
            (doors.length === 1 ? "door" : "doors") + " · " + wall;
        });
        setSecretSummaries((current) => ({ ...current, [depth]: lines }));
      }).catch(() => undefined);
    }
    return () => { active = false; };
  }, [result?.seed.code, result?.selectedTrinket, renderedChallenges, floors]);

  // `?? []` guards against cached worker responses from before quests existed.
'''
if "setSecretSummaries({});" not in s:
    if needle not in s: raise SystemExit("floors anchor changed")
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
    if render not in s: raise SystemExit("floor render anchor changed")
    s=s.replace(render,summary,1)
p.write_text(s)

p=root/"web/src/designs/one/floor-map-inline.css"
css='''
/* Seed Seeker Plus: secret locator visible without opening map */
.d1-plus-floor-secret-summary {
  margin: 5px 12px 7px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.4;
  background: color-mix(in srgb, var(--region) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--region) 28%, transparent);
}
'''
cs=p.read_text()
if "secret locator visible without opening map" not in cs: p.write_text(cs+css)
print("Applied floor-level secret summary")
