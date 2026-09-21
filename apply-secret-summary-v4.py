#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "app")
p = root / "web/src/designs/one/LevelMapView.tsx"
s = p.read_text(encoding="utf-8")

anchor = '''  const toolbar = (
    <div className="d1-map-toolbar">
'''
insert = '''  const secretSummary =
    bundle && branch === 0 && bundle.map.secretRooms.length > 0
      ? bundle.map.secretRooms.map((room, index) => {
          const [left, top, right, bottom] = room;
          const doors = bundle.map.secretDoors.filter((cell) => {
            const x = cell % bundle.map.width;
            const y = Math.floor(cell / bundle.map.width);
            return x >= left && x <= right && y >= top && y <= bottom;
          });
          const door = doors[0];
          let wall = "?";
          if (door !== undefined) {
            const x = door % bundle.map.width;
            const y = Math.floor(door / bundle.map.width);
            wall = y === top ? "N" : y === bottom ? "S" : x === left ? "W" : x === right ? "E" : "?";
          }
          return "Secret room " + (index + 1) + " · " + doors.length + " " +
            (doors.length === 1 ? "door" : "doors") + " · " + wall;
        })
      : [];

'''
if insert not in s:
    if anchor not in s:
        raise SystemExit("LevelMapView toolbar anchor changed")
    s = s.replace(anchor, insert + anchor, 1)

anchor2 = '''      {toolbar}
      <div className="d1-map-stage">
'''
insert2 = '''      {toolbar}
      {secretSummary.length > 0 && (
        <div className="d1-map-secret-summary">
          {secretSummary.map((line) => <div key={line}>{line}</div>)}
        </div>
      )}
      <div className="d1-map-stage">
'''
if insert2 not in s:
    if anchor2 not in s:
        raise SystemExit("LevelMapView render anchor changed")
    s = s.replace(anchor2, insert2, 1)
p.write_text(s, encoding="utf-8")

p = root / "web/src/designs/one/level-map.css"
s = p.read_text(encoding="utf-8")
css = '''
/* Seed Seeker Plus: concise secret-room locator */
.d1-map-secret-summary {
  margin: 0 12px 8px;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
  background: color-mix(in srgb, var(--region) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--region) 30%, transparent);
}
'''
if "Seed Seeker Plus: concise secret-room locator" not in s:
    p.write_text(s + css, encoding="utf-8")

print("Applied concise secret-room summary")
