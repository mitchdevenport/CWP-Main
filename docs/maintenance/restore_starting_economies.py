"""Restore the 1946 economies that the generated building history left empty.

The building history (common/history/buildings) was regenerated in 2026 from a game state in which some countries
owned nothing but government buildings: Czechoslovakia, Yugoslavia, Romania, Bulgaria, Albania, North Korea and French
West Africa had administration, universities and barracks, but no farms, mines or industries, so their economies
collapsed within months (default, starvation). CWP 1.5's building history gave these states a working economy. For
every state whose owner has no economic building in the generated history, this script rebuilds the economic
buildings that state had in CWP 1.5:

* building types this version no longer has are mapped (fuel refineries -> oil refineries, shipyards -> shipyard) or
  dropped (hospitals, rubber, silk, opium and phosphorus);
* levels are scaled by how much the generated history scaled each building type for the countries it kept;
* farms the state region does not allow are switched to an allowed crop; levels are capped by the state's resources
  and arable land;
* production methods are CWP 1.5's where they still exist, otherwise the ones the generated history uses most for
  that building in countries with the same starting production technologies, checked against the country's starting
  technologies and laws;
* the government owns the buildings, as the generated history does for these countries.

The restored buildings are marked with comments, so the script can be run again (it replaces its own output). Run it
from the mod root after the building history is regenerated and review the diff:

    python docs/maintenance/restore_starting_economies.py [--ref origin/master] [--game "D:/Steam/steamapps/common/Victoria 3"]

--ref is a git revision of CWP 1.5 (the master branch of the CWP repository).
"""
import argparse
import collections
import glob
import math
import os
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--ref", default="origin/master", help="git revision of CWP 1.5")
parser.add_argument("--game", default=r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3")
parser.add_argument("--mod", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
parser.add_argument("--dry-run", action="store_true", help="report only, do not write")
ARGS = parser.parse_args()
MOD = ARGS.mod
GAME = os.path.join(ARGS.game, "game")
HISTORY = os.path.join(MOD, "common", "history", "buildings")

BEGIN = "# CWP 1.5 starting economy (docs/maintenance/restore_starting_economies.py)"
END = "# end of CWP 1.5 starting economy"

# Government buildings: the generated history kept these, they are not part of the economy
GOVERNMENT = {
    "building_government_administration", "building_barrack", "building_naval_administration", "building_university",
    "building_naval_base", "building_conscription_center", "building_army_logistics_center",
    "building_naval_logistics_center", "building_air_base",
}
# CWP 1.5 building types this version replaced or removed
RENAMED = {"building_fuel_refineries": "building_oil_refineries", "building_shipyards": "building_shipyard"}
GRAIN = ["building_wheat_farm", "building_rye_farm", "building_maize_farm", "building_millet_farm", "building_rice_farm"]
MIN_MASTER_LEVELS = 5  # restore a state only if CWP 1.5 had at least this many economic building levels there


# ---------------------------------------------------------------- parsing helpers
def read(path):
    return open(path, encoding="utf-8-sig", errors="replace").read()


def strip_comments(text):
    return re.sub(r"#[^\n]*", "", text)


def block_end(text, start):
    """Index just past the brace block opening at text[start] == '{'."""
    depth = 0
    quoted = False
    for i in range(start, len(text)):
        c = text[i]
        if c == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced braces")


def children(text, pattern):
    """(match, body start, body end) for every 'key = {' matching pattern at the top level of text."""
    out = []
    pos = 0
    rx = re.compile(pattern)
    while True:
        m = rx.search(text, pos)
        if not m:
            return out
        start = m.end() - 1
        end = block_end(text, start)
        out.append((m, start, end))
        pos = end


def top_blocks(text):
    for m, start, end in children(text, r"(?m)^([A-Za-z0-9_\.:]+)\s*=\s*\{"):
        yield m.group(1), text[start:end]


def game_and_mod_files(sub):
    files = {}
    for root in (GAME, MOD):
        for path in glob.glob(os.path.join(root, sub, "*.txt")):
            files[os.path.basename(path).lower()] = path  # the mod's file replaces the game's file of the same name
    return sorted(files.values())


def git(*args):
    return subprocess.run(["git", *args], cwd=MOD, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout


def building_entries(text):
    """{(state, owner): [entry]} where entry = {type, level, pms}; government ownership levels are summed."""
    out = collections.defaultdict(list)
    for sm, s_start, s_end in children(text, r"s:(STATE_\w+)\s*=\s*\{"):
        state_text = text[s_start:s_end]
        for rm, r_start, r_end in children(state_text[1:], r"region_state:(\w+)\s*=\s*\{"):
            region = state_text[1:][r_start:r_end]
            for _, b_start, b_end in children(region[1:], r"create_building\s*=\s*\{"):
                body = region[1:][b_start:b_end]
                btype = re.search(r'\bbuilding\s*=\s*"?(\w+)"?', body).group(1)
                level = re.search(r"\blevel\s*=\s*(\d+)", body)
                levels = int(level.group(1)) if level else sum(int(x) for x in re.findall(r"\blevels\s*=\s*(\d+)", body))
                pms = re.search(r"activate_production_methods\s*=\s*\{([^}]*)\}", body)
                out[(sm.group(1), rm.group(1))].append({
                    "type": btype, "level": levels,
                    "pms": re.findall(r'"?(pm_\w+)"?', pms.group(1)) if pms else [],
                })
    return out


# ---------------------------------------------------------------- game data
def load_buildings():
    buildings, groups, methods = {}, {}, {}
    for path in game_and_mod_files(os.path.join("common", "buildings")):
        for name, body in top_blocks(strip_comments(read(path))):
            if not name.startswith("building_"):
                continue
            pmg = re.search(r"production_method_groups\s*=\s*\{([^}]*)\}", body)
            group = re.search(r"\bbuilding_group\s*=\s*(\w+)", body)
            techs = re.search(r"unlocking_technologies\s*=\s*\{([^}]*)\}", body)
            buildings[name] = {
                "pmgs": pmg.group(1).split() if pmg else [],
                "group": group.group(1) if group else None,
                "techs": techs.group(1).split() if techs else [],
            }
    for path in game_and_mod_files(os.path.join("common", "production_method_groups")):
        for name, body in top_blocks(strip_comments(read(path))):
            pms = re.search(r"production_methods\s*=\s*\{([^}]*)\}", body)
            groups[name] = pms.group(1).split() if pms else []
    for path in game_and_mod_files(os.path.join("common", "production_methods")):
        for name, body in top_blocks(strip_comments(read(path))):
            def ids(key):
                m = re.search(key + r"\s*=\s*\{([^}]*)\}", body)
                return m.group(1).split() if m else []
            methods[name] = {"techs": ids("unlocking_technologies"), "laws": ids("unlocking_laws"),
                             "disallowing": ids("disallowing_laws")}
    return buildings, groups, methods


def load_state_regions():
    regions = {}
    for path in game_and_mod_files(os.path.join("map_data", "state_regions")):
        for name, body in top_blocks(strip_comments(read(path))):
            if not name.startswith("STATE_"):
                continue
            arable = re.search(r"\barable_land\s*=\s*(\d+)", body)
            arable_groups = re.search(r"arable_resources\s*=\s*\{([^}]*)\}", body)
            capped = re.search(r"capped_resources\s*=\s*\{([^}]*)\}", body)
            discovered = {}
            for _, start, end in children(body[1:], r"\bresource\s*=\s*\{"):
                res = body[1:][start:end]
                rtype = re.search(r'type\s*=\s*"?(\w+)"?', res)
                amount = re.search(r"discovered_amount\s*=\s*(\d+)", res)
                if rtype:
                    discovered[rtype.group(1)] = int(amount.group(1)) if amount else 0
            regions[name] = {
                "arable_land": int(arable.group(1)) if arable else 0,
                "arable_groups": set(arable_groups.group(1).replace('"', "").split()) if arable_groups else set(),
                "capped": {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", capped.group(1))} if capped else {},
                "discovered": discovered,
                "port": bool(re.search(r"\bport\s*=\s*x[0-9A-Fa-f]+", body)),
            }
    return regions


def load_country_setup():
    """{tag: {"tier": production tier effect, "techs": set, "laws": set}} from the country history files."""
    effects = {}
    for path in glob.glob(os.path.join(MOD, "common", "scripted_effects", "*.txt")):
        for name, body in top_blocks(strip_comments(read(path))):
            if name.startswith("effect_starting_"):
                effects[name] = body
    setup = {}
    for path in glob.glob(os.path.join(MOD, "common", "history", "countries", "*.txt")):
        text = strip_comments(read(path))
        for m, start, end in children(text, r"c:(\w+)\s*\??=\s*\{"):
            body = text[start:end]
            calls = re.findall(r"\b(effect_starting_\w+)\s*=\s*yes", body)
            techs = set(re.findall(r"add_technology_researched\s*=\s*(\w+)", body))
            laws = set(re.findall(r"activate_law\s*=\s*law_type:(\w+)", body))
            pending, seen = list(calls), set()
            while pending:  # law packages can call other packages
                call = pending.pop()
                if call in seen:
                    continue
                seen.add(call)
                techs |= set(re.findall(r"add_technology_researched\s*=\s*(\w+)", effects.get(call, "")))
                laws |= set(re.findall(r"activate_law\s*=\s*law_type:(\w+)", effects.get(call, "")))
                pending += re.findall(r"\b(effect_starting_\w+)\s*=\s*yes", effects.get(call, ""))
            tier = next((c for c in calls if c.startswith("effect_starting_production_technologies")), None)
            entry = setup.setdefault(m.group(1), {"tier": None, "techs": set(), "laws": set()})
            entry["tier"] = entry["tier"] or tier
            entry["techs"] |= techs
            entry["laws"] |= laws
    return setup


def state_owners():
    owners = collections.defaultdict(set)
    for path in glob.glob(os.path.join(MOD, "common", "history", "states", "*.txt")):
        text = strip_comments(read(path))
        for m, start, end in children(text, r"s:(STATE_\w+)\s*=\s*\{"):
            for c in re.finditer(r"create_state\s*=\s*\{\s*country\s*=\s*c:(\w+)", text[start:end]):
                owners[m.group(1)].add(c.group(1))
    return owners


# ---------------------------------------------------------------- main
def remove_previous_output(text):
    return re.sub(r"\n[\t ]*" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"[^\n]*", "", text, flags=re.S)


def main():
    buildings, groups, methods = load_buildings()
    regions = load_state_regions()
    setup = load_country_setup()
    owners = state_owners()

    head_files = {}
    head = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(HISTORY, "*.txt"))):
        raw = open(path, "rb").read().decode("utf-8-sig")
        text = remove_previous_output(raw.replace("\r\n", "\n"))
        head_files[path] = text
        for key, entries in building_entries(text).items():
            head[key].extend(entries)

    master = collections.defaultdict(list)
    for name in git("ls-tree", "--name-only", ARGS.ref, "common/history/buildings/").split():
        if name.endswith(".txt"):
            for key, entries in building_entries(git("show", ARGS.ref + ":" + name).lstrip("\ufeff")).items():
                master[key].extend(entries)

    def economy(entries):
        return sum(e["level"] for e in entries if e["type"] not in GOVERNMENT)

    targets = sorted(k for k, entries in master.items()
                     if economy(entries) >= MIN_MASTER_LEVELS and economy(head.get(k, [])) == 0
                     and k[1] in owners.get(k[0], set()))
    restored_tags = {tag for _, tag in targets}

    # How the generated history scaled each building type, over the countries it kept
    total_master, total_head = collections.Counter(), collections.Counter()
    for (state, tag), entries in master.items():
        if tag not in restored_tags:
            for e in entries:
                total_master[RENAMED.get(e["type"], e["type"])] += e["level"]
    for (state, tag), entries in head.items():
        if tag not in restored_tags:
            for e in entries:
                total_head[e["type"]] += e["level"]

    def scale(btype):
        if total_master[btype] < 20 or total_head[btype] == 0:
            return 1.0
        return min(3.0, max(0.5, total_head[btype] / total_master[btype]))

    # Production methods the generated history uses, by production technology tier
    usage = collections.defaultdict(collections.Counter)  # (tier, building type) -> pm counts
    for (state, tag), entries in head.items():
        tier = setup.get(tag, {}).get("tier")
        for e in entries:
            for pm in e["pms"]:
                usage[(tier, e["type"])][pm] += e["level"]
                usage[(None, e["type"])][pm] += e["level"]

    def usable(pm, tag):
        info = methods.get(pm)
        if info is None:
            return False
        country = setup.get(tag, {"techs": set(), "laws": set()})
        if not set(info["techs"]) <= country["techs"]:
            return False
        if info["laws"] and not set(info["laws"]) & country["laws"]:
            return False
        return not set(info["disallowing"]) & country["laws"]

    def choose_pms(btype, tag, master_pms):
        chosen = []
        tier = setup.get(tag, {}).get("tier")
        for pmg in buildings[btype]["pmgs"]:
            options = groups.get(pmg, [])
            pick = next((pm for pm in master_pms if pm in options and usable(pm, tag)), None)
            for counts in (usage[(tier, btype)], usage[(None, btype)]):
                if pick:
                    break
                ranked = sorted((pm for pm in options if counts[pm]), key=lambda pm: -counts[pm])
                pick = next((pm for pm in ranked if usable(pm, tag)), None)
            if not pick:
                pick = next((pm for pm in reversed(options) if usable(pm, tag)), None)
            if not pick and options:
                # every option needs a technology the country lacks: the generated history uses the most common
                # option anyway (the group's first one by default), so do the same
                counts = usage[(None, btype)]
                pick = max(options, key=lambda pm: (counts[pm], -options.index(pm)))
            if pick:
                chosen.append(pick)
        return chosen

    report = collections.defaultdict(collections.Counter)
    notes = []
    inserts = collections.defaultdict(list)  # (state, tag) -> text
    for state, tag in targets:
        region = regions.get(state)
        if region is None:
            notes.append(f"{state}: no state region, skipped")
            continue
        country = setup.get(tag, {"techs": set(), "laws": set()})
        used = collections.Counter()  # levels other owners already have in this state
        for (s, other), entries in head.items():
            if s == state:
                for e in entries:
                    used[e["type"]] += e["level"]
        arable_used = sum(v for t, v in used.items() if buildings.get(t, {}).get("group") in region["arable_groups"])

        wanted = collections.Counter()
        master_pms = {}
        for e in master[(state, tag)]:
            btype = RENAMED.get(e["type"], e["type"])
            if btype in GOVERNMENT or e["level"] <= 0:
                continue
            if btype not in buildings:
                notes.append(f"{tag} {state}: {e['type']} no longer exists, dropped {e['level']} levels")
                continue
            if buildings[btype]["techs"] and not set(buildings[btype]["techs"]) <= country["techs"]:
                notes.append(f"{tag} {state}: {btype} needs {buildings[btype]['techs']}, dropped")
                continue
            group = buildings[btype]["group"]
            if btype in GRAIN and group not in region["arable_groups"]:
                allowed = [g for g in GRAIN if buildings.get(g, {}).get("group") in region["arable_groups"]]
                if not allowed:
                    notes.append(f"{tag} {state}: no grain farm allowed, dropped {btype}")
                    continue
                notes.append(f"{tag} {state}: {btype} not allowed, became {allowed[0]}")
                btype = allowed[0]
            wanted[btype] += max(1, round(e["level"] * scale(btype)))
            master_pms.setdefault(btype, [pm for pm in e["pms"]])

        # caps
        final = collections.Counter()
        arable = {}
        for btype, level in wanted.items():
            group = buildings[btype]["group"]
            if group in region["arable_groups"]:
                arable[btype] = level
                continue
            if btype in region["capped"]:
                cap = region["capped"][btype] - used[btype]
            elif btype in region["discovered"]:
                cap = region["discovered"][btype] - used[btype]
            elif any(btype in r["capped"] or btype in r["discovered"] for r in regions.values()) \
                    or any(group in r["arable_groups"] for r in regions.values()):
                cap = 0  # a resource this state does not have
            elif btype == "building_port" and not region["port"]:
                cap = 0
            else:
                cap = level
            if cap < level:
                notes.append(f"{tag} {state}: {btype} capped {level} -> {max(cap, 0)}")
            if cap > 0:
                final[btype] = min(level, cap)
        room = region["arable_land"] - arable_used
        total = sum(arable.values())
        if total > room:
            notes.append(f"{tag} {state}: arable buildings {total} > arable land {room}, scaled down")
            factor = max(room, 0) / total
            arable = {t: math.floor(v * factor) for t, v in arable.items()}
        for btype, level in arable.items():
            if level > 0:
                final[btype] = level

        lines = ["\t\t\t" + BEGIN]
        for btype in sorted(final, key=lambda t: (-final[t], t)):
            pms = choose_pms(btype, tag, master_pms.get(btype, []))
            if len(pms) < len(buildings[btype]["pmgs"]):
                notes.append(f"{tag} {state}: {btype} has no usable production method in some groups")
            report[tag][btype] += final[btype]
            lines += [
                "\t\t\tcreate_building={",
                f'\t\t\t\tbuilding="{btype}"',
                "\t\t\t\tadd_ownership={",
                "\t\t\t\t\tcountry={",
                f'\t\t\t\t\t\tcountry="c:{tag}"',
                f"\t\t\t\t\t\tlevels={final[btype]}",
                "\t\t\t\t\t}",
                "\t\t\t\t}",
                "\t\t\t\treserves=1",
                "\t\t\t\tactivate_production_methods={ " + " ".join(f'"{pm}"' for pm in pms) + " }",
                "\t\t\t}",
            ]
        lines.append("\t\t\t" + END)
        inserts[(state, tag)] = "\n".join(lines)

    # write: append to the end of each target region_state block
    for path, text in head_files.items():
        edits = []
        for sm, s_start, s_end in children(text, r"s:(STATE_\w+)\s*=\s*\{"):
            for rm, r_start, r_end in children(text[s_start + 1:s_end], r"region_state:(\w+)\s*=\s*\{"):
                key = (sm.group(1), rm.group(1))
                if key in inserts:
                    close = s_start + 1 + r_end - 1  # index of the region_state block's closing brace
                    line_start = text.rfind("\n", 0, close) + 1
                    edits.append((line_start, inserts.pop(key) + "\n"))
        new = text
        for pos, insert in sorted(edits, reverse=True):
            new = new[:pos] + insert + new[pos:]
        original = open(path, "rb").read().decode("utf-8-sig").replace("\r\n", "\n")
        if new != original and not ARGS.dry_run:
            open(path, "wb").write(b"\xef\xbb\xbf" + new.replace("\n", "\r\n").encode("utf-8"))
    for key in inserts:
        notes.append(f"{key}: no region_state block found, not written")

    for tag in sorted(report):
        print(f"{tag}: {sum(report[tag].values())} levels: " + ", ".join(f"{t[9:]} {v}" for t, v in report[tag].most_common()))
    for note in notes:
        print("  note:", note)


main()
