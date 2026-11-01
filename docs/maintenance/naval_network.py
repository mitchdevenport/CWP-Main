"""Adapt vanilla's precomputed naval travel network to the CWP map.

Victoria 3 1.14 moves fleets along a precomputed waypoint graph loaded from
``common/travel_network/naval_network.txt``. Vanilla ships one generated for the
vanilla map, and the developer tool that generates it is not available in
release builds. The CWP map is derived from the vanilla map but splits the
oceans into many more sea regions (sea lanes), marks open ocean as impassable
and moves some coastlines, so the vanilla graph is only partly valid for it:
the game discards nodes that point at missing/non-sea provinces, nodes keep the
vanilla province they were generated for, and some connections run straight
through sea regions CWP made impassable.

This script rebuilds the file from the vanilla graph for the CWP map:

* port waypoints ("harbor_from_spline") are moved to CWP's port locators, which
  is where CWP's spline network has its port anchors (locator id = state id);
  new CWP ports get one, and vanilla ports CWP does not have become plain
  harbors. Route waypoints ("sea_from_spline") that do not lie on a CWP naval
  route anchor become plain sea waypoints;
* every waypoint is kept on passable sea (the game derives the sea province
  from the waypoint position);
* every sea waypoint is assigned to the CWP sea province it actually lies in
  (waypoints that ended up on land are nudged to the nearest sea pixel,
  waypoints inside impassable seas are removed);
* harbor waypoints whose province is no longer coastal land are re-assigned to
  the nearest coastal CWP province;
* connections crossing impassable sea regions are removed;
* every state port gets a harbor waypoint, and every sea region used as a
  naval exit gets at least one waypoint (vanilla has none in some open-ocean
  regions that CWP uses as naval exits, e.g. the Azores).

Run it from the mod root after changing the map or after a game update that
changes the vanilla network, and commit the result:

    python docs/maintenance/naval_network.py            # report + write
    python docs/maintenance/naval_network.py --check    # report only

Requires numpy and Pillow.
"""
import argparse
import glob
import math
import os
import re
import struct
import sys
from collections import Counter, deque

import numpy as np
from PIL import Image

DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3"
REL_PATH = os.path.join("common", "travel_network", "naval_network.txt")
SEA_TYPES = ("sea", "sea_from_spline")
NUDGE_RADIUS = 6             # how far (map pixels) a waypoint may be moved to get back onto passable sea
HARBOR_SEARCH_RADIUS = 12    # how far to look for a coastal province for an orphaned harbor waypoint
NEW_LINKS = 3                # connections created for each new sea waypoint
PORT_LINKS = 2               # connections created for each new or moved port waypoint
LOCATOR_MATCH_DISTANCE = 8   # vanilla port waypoints lie within a few pixels of their port locator
ANCHOR_MATCH_DISTANCE = 3    # spline-derived waypoints lie on an anchor of the spline network
PORT_SEARCH_RADIUS = 12      # how far from its locator a port waypoint may be placed to reach passable sea
RELINK_DISTANCE = 10         # port waypoints moved further than this get new connections

Image.MAX_IMAGE_PIXELS = None


def strip_comments(text):
    return re.sub(r"#[^\n]*", "", text)


def hex_list(text):
    return [c.upper() for c in re.findall(r"x([0-9A-Fa-f]{6})", text)]


def read_text(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def top_level_blocks(text):
    """Yield (key, body) for every `KEY = { ... }` block at the top level of a script file."""
    depth, key, start = 0, None, 0
    for m in re.finditer(r"([A-Za-z0-9_]+)\s*=\s*\{|\{|\}", text):
        tok = m.group(0)
        if tok.endswith("{"):
            if depth == 0 and m.group(1):
                key, start = m.group(1), m.end()
            depth += 1
        else:
            depth -= 1
            if depth == 0 and key:
                yield key, text[start:m.start()]
                key = None


class MapData:
    def __init__(self, root):
        default_map = strip_comments(read_text(os.path.join(root, "map_data", "default.map")))
        self.seas = set(hex_list(re.search(r"sea_starts\s*=\s*\{(.*?)\}", default_map, re.S).group(1)))
        lakes = re.search(r"lakes\s*=\s*\{(.*?)\}", default_map, re.S)
        self.lakes = set(hex_list(lakes.group(1))) if lakes else set()

        self.impassable = set()
        self.state_of = {}
        self.states = {}
        for path in glob.glob(os.path.join(root, "map_data", "state_regions", "*.txt")):
            for name, body in top_level_blocks(strip_comments(read_text(path))):
                provinces = re.search(r"provinces\s*=\s*\{([^}]*)\}", body)
                if not provinces:
                    continue
                state = {"name": name, "provinces": set(hex_list(provinces.group(1)))}
                ident = re.search(r"\bid\s*=\s*(\d+)", body)
                state["id"] = int(ident.group(1)) if ident else None
                port = re.search(r"\bport\s*=\s*\"?x([0-9A-Fa-f]{6})", body)
                state["port"] = port.group(1).upper() if port else None
                exit_id = re.search(r"naval_exit_id\s*=\s*(\d+)", body)
                state["naval_exit"] = int(exit_id.group(1)) if exit_id else None
                for m in re.finditer(r"impassable\s*=\s*\{([^}]*)\}", body):
                    self.impassable |= set(hex_list(m.group(1)))
                self.states[name] = state
                for p in state["provinces"]:
                    self.state_of[p] = name
        self.state_by_id = {s["id"]: s for s in self.states.values() if s["id"] is not None}

        rgb = np.asarray(Image.open(os.path.join(root, "map_data", "provinces.png")).convert("RGB"))
        self.key = (rgb[:, :, 0].astype(np.int32) << 16) | (rgb[:, :, 1].astype(np.int32) << 8) | rgb[:, :, 2]
        self.height, self.width = self.key.shape
        self.passable_seas = self.seas - self.impassable
        self.sea_mask = np.isin(self.key, [int(s, 16) for s in self.seas])
        self.passable_mask = np.isin(self.key, [int(s, 16) for s in self.passable_seas])
        self.impassable_sea_mask = self.sea_mask & ~self.passable_mask
        lake_mask = np.isin(self.key, [int(s, 16) for s in self.lakes])
        near_sea = self._dilate(self.passable_mask)
        land_mask = ~self.sea_mask & ~lake_mask & ~np.isin(self.key, [int(p, 16) for p in self.impassable])
        # harbors need passable coastal land: the game cannot dock at impassable provinces
        self.coastal_land = {"%06X" % v for v in np.unique(self.key[near_sea & land_mask]).tolist()}
        self.coastal_land_mask = np.isin(self.key, [int(p, 16) for p in self.coastal_land]) & near_sea
        self.present = {"%06X" % v for v in np.unique(self.key).tolist()}

    @staticmethod
    def _dilate(mask):
        out = mask.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            shifted = np.roll(mask, dx, axis=1)  # the map wraps horizontally
            if dy > 0:
                shifted = np.vstack([np.zeros((dy, mask.shape[1]), bool), shifted[:-dy]])
            elif dy < 0:
                shifted = np.vstack([shifted[-dy:], np.zeros((-dy, mask.shape[1]), bool)])
            out |= shifted
        return out

    def row(self, y):
        """Network y coordinates count from the bottom of provinces.png."""
        return self.height - 1 - y

    def province_at(self, x, y):
        return "%06X" % self.key[self.row(y), x % self.width]

    def nearest(self, mask, x, y, radius):
        """Nearest pixel (network coordinates) within `radius` where `mask` is set, or None."""
        r0, r1 = max(0, self.row(y) - radius), min(self.height, self.row(y) + radius + 1)
        cols = [(x + dx) % self.width for dx in range(-radius, radius + 1)]
        window = mask[r0:r1][:, cols]
        hits = np.argwhere(window)
        if not len(hits):
            return None
        dist = (hits[:, 0] + r0 - self.row(y)) ** 2 + (hits[:, 1] - radius) ** 2
        r, c = hits[int(np.argmin(dist))]
        return cols[c], self.height - 1 - (r + r0)

    def segment(self, a, b):
        """Pixels (network coordinates) along the straight line a-b, taking the shorter way around the wrap."""
        (ax, ay), (bx, by) = a, b
        if abs(ax - bx) > self.width // 2:
            bx += self.width if ax > bx else -self.width
        steps = max(2, int(max(abs(ax - bx), abs(ay - by))))
        for i in range(steps + 1):
            yield int(round(ax + (bx - ax) * i / steps)) % self.width, int(round(ay + (by - ay) * i / steps))

    def crosses(self, mask, a, b):
        return any(mask[self.row(y), x] for x, y in self.segment(a, b))


def parse_network(text):
    nodes = [
        {"province": m.group(1).upper(), "x": int(m.group(2)), "y": int(m.group(3)), "type": m.group(4)}
        for m in re.finditer(r"province=x([0-9A-Fa-f]{6})\s+x=(-?\d+)\s+y=(-?\d+)\s+type=(\w+)", text)
    ]
    connections = [(int(a), int(b)) for a, b in re.findall(r"from=(\d+)\s+to=(\d+)", text)]
    return nodes, connections


def write_network(path, nodes, connections, header):
    lines = [header, "nodes={ {"]
    lines.append("\t} {\n".join("province=x%s x=%d y=%d type=%s" % (n["province"], n["x"], n["y"], n["type"]) for n in nodes) + "\t} }")
    lines.append("connections={ {")
    lines.append("\t} {\n".join("from=%d to=%d " % c for c in connections) + "\t} }")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def components_by_root(count, connections):
    """Component id (root waypoint index) of every waypoint."""
    parent = list(range(count))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in connections:
        parent[find(a)] = find(b)
    return [find(i) for i in range(count)]


def read_locators(path):
    """Port locators: {id: (x, y)} in network coordinates. Locator ids are the ids of the states they belong to."""
    text = read_text(path)
    return {
        int(m.group(1)): (float(m.group(2)), float(m.group(3)))
        for m in re.finditer(r"id=(\d+)\s+position=\{\s*([-\d.]+)\s+[-\d.]+\s+([-\d.]+)", text)
    }


def read_spline_anchors(path):
    """Positions of all anchors of a binary spline network (.splnet) as an (N, 2) array."""
    with open(path, "rb") as f:
        data = f.read()
    # anchor = { id = <uint32> position = { <float> <float> } } in binary script tokens
    pattern = re.compile(rb"\x0b\x00\x01\x00\x14\x00.{4}\x4c\x00\x01\x00\x03\x00\x0d\x00(.{4})\x0d\x00(.{4})\x04\x00", re.S)
    return np.array([struct.unpack("<ff", m.group(1) + m.group(2)) for m in pattern.finditer(data)], dtype=float)


def adapt(game_root, mod_root, log):
    vanilla_root = os.path.join(game_root, "game")
    vanilla_nodes, vanilla_connections = parse_network(read_text(os.path.join(vanilla_root, REL_PATH)))
    cwp = MapData(mod_root)
    locator_file = os.path.join("gfx", "map", "map_object_data", "generated_map_object_locators_port.txt")
    vanilla_ports = read_locators(os.path.join(vanilla_root, locator_file))
    cwp_ports = read_locators(os.path.join(mod_root, locator_file))
    anchors = read_spline_anchors(os.path.join(mod_root, "gfx", "map", "spline_network", "spline_network.splnet"))
    stats = Counter()

    def near_anchor(x, y):
        return float(np.hypot(anchors[:, 0] - x, anchors[:, 1] - y).min()) <= ANCHOR_MATCH_DISTANCE

    def port_province(state_id):
        state = cwp.state_by_id.get(state_id)
        return state["port"] if state and state["port"] in cwp.coastal_land else None

    # 1. Port waypoints ("harbor_from_spline") sit at the port locators, where the spline network
    #    has its port anchors; sea waypoints of type "sea_from_spline" sit on naval route anchors.
    #    Re-target them to the CWP locators/anchors, and demote those CWP does not have.
    nodes, remap, relink, port_nodes = [], {}, set(), {}
    for index, node in enumerate(vanilla_nodes):
        node = dict(node)
        if node["type"] == "harbor_from_spline":
            dist, state_id = min((math.hypot(node["x"] - x, node["y"] - y), k) for k, (x, y) in vanilla_ports.items())
            if dist <= LOCATOR_MATCH_DISTANCE and state_id in cwp_ports and port_province(state_id) and state_id not in port_nodes:
                spot = cwp.nearest(cwp.passable_mask, int(round(cwp_ports[state_id][0])), int(round(cwp_ports[state_id][1])), PORT_SEARCH_RADIUS)
                if spot is not None:
                    if math.hypot(spot[0] - node["x"], spot[1] - node["y"]) > RELINK_DISTANCE:
                        relink.add(len(nodes))
                        stats["port waypoints moved to the CWP port locator"] += 1
                    node["x"], node["y"], node["province"] = spot[0], spot[1], port_province(state_id)
                    port_nodes[state_id] = len(nodes)
                    remap[index] = len(nodes)
                    nodes.append(node)
                    continue
            if dist <= LOCATOR_MATCH_DISTANCE or not near_anchor(node["x"], node["y"]):
                node["type"] = "harbor"
                stats["port waypoints without a CWP port demoted to harbors"] += 1
        elif node["type"] == "sea_from_spline" and not near_anchor(node["x"], node["y"]):
            node["type"] = "sea"
            stats["route waypoints without a CWP route anchor demoted to sea"] += 1

        # 2. Re-home the remaining waypoints on the CWP map. Every waypoint must lie on passable sea;
        #    sea waypoints belong to the sea province they lie in, harbors to a coastal land province.
        here = cwp.province_at(node["x"], node["y"])
        if here not in cwp.passable_seas:
            if here in cwp.impassable and node["type"] in SEA_TYPES:
                stats["sea waypoints removed (impassable sea)"] += 1
                continue
            spot = cwp.nearest(cwp.passable_mask, node["x"], node["y"], NUDGE_RADIUS)
            if spot is None:
                stats["waypoints removed (no nearby passable sea)"] += 1
                continue
            node["x"], node["y"] = spot
            here = cwp.province_at(*spot)
            stats["waypoints moved back onto passable sea"] += 1
        if node["type"] in SEA_TYPES:
            if here != node["province"]:
                stats["sea waypoints re-assigned to CWP sea province"] += 1
            node["province"] = here
        elif node["province"] not in cwp.coastal_land:
            spot = cwp.nearest(cwp.coastal_land_mask, node["x"], node["y"], HARBOR_SEARCH_RADIUS)
            if spot is None:
                stats["harbor waypoints removed (no coastal province)"] += 1
                continue
            node["province"] = cwp.province_at(*spot)
            stats["harbor waypoints re-assigned to coastal CWP province"] += 1
        remap[index] = len(nodes)
        nodes.append(node)

    # Ports that are new in CWP get a port waypoint at their locator.
    for state_id in sorted(set(cwp_ports) - set(port_nodes)):
        province = port_province(state_id)
        if not province:
            continue
        spot = cwp.nearest(cwp.passable_mask, int(round(cwp_ports[state_id][0])), int(round(cwp_ports[state_id][1])), PORT_SEARCH_RADIUS)
        if spot is None:
            log("  ! port locator %d (%s) is not near passable sea" % (state_id, cwp.state_by_id[state_id]["name"]))
            continue
        port_nodes[state_id] = len(nodes)
        relink.add(len(nodes))
        nodes.append({"province": province, "x": spot[0], "y": spot[1], "type": "harbor_from_spline"})
        stats["port waypoints added for CWP ports"] += 1

    # 3. Keep connections between surviving waypoints that do not cross impassable seas.
    connections, seen = [], set()
    for a, b in vanilla_connections:
        if a not in remap or b not in remap:
            stats["connections removed (waypoint removed)"] += 1
            continue
        a, b = remap[a], remap[b]
        if a == b or (min(a, b), max(a, b)) in seen:
            continue
        if a in relink or b in relink:
            stats["connections removed (port waypoint moved)"] += 1
            continue
        pa, pb = (nodes[a]["x"], nodes[a]["y"]), (nodes[b]["x"], nodes[b]["y"])
        if cwp.crosses(cwp.impassable_sea_mask, pa, pb):
            stats["connections removed (cross impassable sea)"] += 1
            continue
        seen.add((min(a, b), max(a, b)))
        connections.append((a, b))

    def link(a, b):
        if a != b and (min(a, b), max(a, b)) not in seen:
            seen.add((min(a, b), max(a, b)))
            connections.append((a, b))
            return True
        return False

    def nearest_nodes(x, y, predicate, limit):
        """Closest sea waypoints reachable from (x, y) over passable water, nearest (by sailing distance) first."""
        by_pixel = {}
        for i, n in enumerate(nodes):
            if n["type"] in SEA_TYPES and predicate(i):
                by_pixel.setdefault((n["x"] % cwp.width, cwp.row(n["y"])), []).append(i)
        start = (x % cwp.width, cwp.row(y))
        visited = np.zeros(cwp.passable_mask.shape, bool)
        visited[start[1], start[0]] = True
        queue, out = deque([start]), []
        while queue and len(out) < limit:
            px, py = queue.popleft()
            out.extend(by_pixel.get((px, py), [])[: limit - len(out)])
            for nx, ny in (((px + 1) % cwp.width, py), ((px - 1) % cwp.width, py), (px, py + 1), (px, py - 1)):
                if 0 <= ny < cwp.height and not visited[ny, nx] and cwp.passable_mask[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))
        return out

    for i in sorted(relink):
        for j in nearest_nodes(nodes[i]["x"], nodes[i]["y"], lambda k: True, PORT_LINKS):
            link(i, j)
            stats["connections added"] += 1

    # 4. Every state port needs a harbor waypoint, and every naval exit sea region used by a port needs
    #    at least one sea waypoint (the coastal renderer and fleet docking look for them). Vanilla does not
    #    require the harbor to connect straight into the exit region, so existing links are left alone.
    harbors_of, sea_provinces = {}, set()
    for i, n in enumerate(nodes):
        if n["type"] in SEA_TYPES:
            sea_provinces.add(n["province"])
        else:
            harbors_of.setdefault(n["province"], []).append(i)
    for state in sorted(cwp.states.values(), key=lambda s: s["name"]):
        port, exit_state = state["port"], cwp.state_by_id.get(state["naval_exit"])
        if not port or not exit_state or port not in cwp.coastal_land:
            continue
        exit_provinces = exit_state["provinces"] & cwp.passable_seas
        if not exit_provinces:
            continue
        exit_mask = np.isin(cwp.key, [int(p, 16) for p in exit_provinces])
        harbors = harbors_of.get(port, [])
        if not harbors:
            # put a harbor waypoint on the water next to the port province, preferring the exit region
            port_mask = cwp.key == int(port, 16)
            ys, xs = np.nonzero(port_mask)
            cx, cy = int(xs.mean()), cwp.height - 1 - int(ys.mean())
            shore = cwp._dilate(port_mask)
            spot = cwp.nearest(exit_mask & shore, cx, cy, 400) or cwp.nearest(cwp.passable_mask & shore, cx, cy, 400)
            if spot is None:
                log("  ! %s: port x%s does not touch passable sea" % (state["name"], port))
                continue
            nodes.append({"province": port, "x": spot[0], "y": spot[1], "type": "harbor"})
            harbors = harbors_of[port] = [len(nodes) - 1]
            for j in nearest_nodes(spot[0], spot[1], lambda i: True, 1):
                link(harbors[0], j)
                stats["connections added"] += 1
            stats["harbor waypoints added for state ports"] += 1
            log("  added harbor for %s (x%s)" % (state["name"], port))
        if exit_provinces & sea_provinces:
            continue
        # vanilla has no waypoint in this sea region: add one offshore near the port and hook it up
        hx, hy = nodes[harbors[0]]["x"], nodes[harbors[0]]["y"]
        spot = cwp.nearest(exit_mask & ~cwp._dilate(~cwp.passable_mask), hx, hy, 200)
        if spot is None:
            log("  ! %s: no open water in naval exit %s near its port" % (state["name"], exit_state["name"]))
            continue
        new = len(nodes)
        nodes.append({"province": cwp.province_at(*spot), "x": spot[0], "y": spot[1], "type": "sea"})
        sea_provinces.add(nodes[new]["province"])
        stats["sea waypoints added in naval exit regions"] += 1
        link(new, harbors[0])
        stats["connections added"] += 1
        for j in nearest_nodes(spot[0], spot[1], lambda i: i != new, NEW_LINKS):
            link(new, j)
            stats["connections added"] += 1
        log("  added a waypoint in %s for %s" % (exit_state["name"], state["name"]))

    # 5. Re-attach fragments that lost their link to the rest of their vanilla group (because a vanilla
    #    connection crossed a CWP impassable sea or ran to a moved port waypoint). Separate groups that
    #    vanilla already has, e.g. the Black Sea, are joined to the rest at runtime by the naval routes of
    #    the spline network, so they are kept apart as in vanilla.
    vanilla_roots = components_by_root(len(vanilla_nodes), vanilla_connections)
    original = {new: old for old, new in remap.items()}
    while True:
        roots = components_by_root(len(nodes), connections)
        sizes = Counter(roots)
        main = max(sizes, key=sizes.get)
        home = {}  # vanilla group -> the new component holding most of it
        for group, members in Counter((vanilla_roots[original[i]], roots[i]) for i in original).most_common():
            home.setdefault(group[0], group[1])
        fragment = None
        for root in sorted(sizes, key=sizes.get):
            members = [i for i, r in enumerate(roots) if r == root]
            groups = Counter(vanilla_roots[original[i]] for i in members if i in original)
            target = home[groups.most_common(1)[0][0]] if groups else main
            if target != root:
                fragment = (members, target)
                break
        if fragment is None:
            break
        members, target = fragment
        start = next((i for i in members if nodes[i]["type"] in SEA_TYPES), members[0])
        found = nearest_nodes(nodes[start]["x"], nodes[start]["y"], lambda i: roots[i] == target, 1)
        if not found:
            log("  ! %d waypoints near (%d, %d) cannot reach the rest of their group" % (len(members), nodes[start]["x"], nodes[start]["y"]))
            break
        link(start, found[0])
        stats["connections added"] += 1
        stats["fragments re-attached to their group"] += 1

    # 6. Report.
    sizes = sorted(Counter(components_by_root(len(nodes), connections)).values(), reverse=True)
    linked = {i for c in connections for i in c}
    isolated = [i for i in range(len(nodes)) if i not in linked]
    covered = {n["province"] for n in nodes if n["type"] in SEA_TYPES}
    empty = sorted(cwp.passable_seas - covered)
    for k in sorted(stats):
        log("  %-55s %d" % (k, stats[k]))
    log("  waypoints %d -> %d, connections %d -> %d" % (len(vanilla_nodes), len(nodes), len(vanilla_connections), len(connections)))
    log("  graph components (largest first): %s, isolated waypoints: %d" % (sizes[:8], len(isolated)))
    log("  passable sea provinces without waypoints (open ocean, as in vanilla): %d" % len(empty))
    return nodes, connections


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", default=DEFAULT_GAME, help="Victoria 3 install folder (containing game/)")
    parser.add_argument("--mod", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    parser.add_argument("--check", action="store_true", help="only report, do not write")
    args = parser.parse_args()
    if not os.path.isfile(os.path.join(args.game, "game", REL_PATH)):
        sys.exit("Vanilla naval network not found under " + args.game)
    print("Adapting vanilla naval network to the CWP map:")
    nodes, connections = adapt(args.game, args.mod, print)
    if not args.check:
        out = os.path.join(args.mod, REL_PATH)
        write_network(out, nodes, connections,
                      "# Generated by docs/maintenance/naval_network.py from the vanilla naval network for the CWP map. Do not edit by hand.")
        print("Wrote", out)


if __name__ == "__main__":
    main()
