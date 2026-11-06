"""Restore CWP 1.5's flavour events from the base game.

CWP 1.5 shipped its own copies of the base game's generic flavour events (law debates, election campaigns,
revolutions, exiles, decrees, natural disasters, border incidents, IG leaders and petitions, ...). They went stale
as the base game changed and were disabled, so this script rebuilds them from the installed base game:

* events/...: the base game's event files CWP 1.5 had, limited to the events CWP 1.5 used and adapted to CWP
  (CWP's buildings, laws and goods; the 19th-century technologies every 1946 country has; a few base game bugs);
* common/static_modifiers|scripted_triggers|scripted_effects|script_values/cwp_vanilla_event_*.txt: the base game
  definitions those events need (the mod blanks the base game's files in these folders);
* common/on_actions/cwp_flavour_events_on_actions.txt: the base game's hooks for them (with CWP 1.5's weights),
  called from common/on_actions/00_code_on_actions.txt.

Run it from the mod root after every game update and review the diff:

    python docs/maintenance/restore_flavour_events.py [--game "D:/Steam/steamapps/common/Victoria 3"]
"""
import argparse
import glob
import os
import re

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--game", default=r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3")
parser.add_argument("--mod", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
ARGS = parser.parse_args()
V14 = os.path.join(ARGS.game, "game")
TARGET = ARGS.mod

# The base game's event files CWP 1.5 had (relative to events/, without .txt)
CANDS = """
agitators_events/agitator_law_events_2
agitators_events/agitators_law_events
agitators_events/exiles_events
agitators_events/exiles_events_02
agitators_events/revolution_events_01
agitators_events/revolution_events_02
agitators_events/revolution_events_03
agitators_events/yeet_agitator_events
autocracy_events
commander_events
communism
crime_events
cultural_homeland_events
decree_events
decree_events_02
diplomatic_friction_events
fascism_events
general_events
government_conflicts_events
ig_leaders
ig_petitions
ig_revolutions
natural_disasters_events
neighbor_events
obligation_events
prostitution_events
psychology_events
secession_situations
election_events/communist_fascist_election_events
election_events/election_conservative_events
election_events/election_contextual_events
election_events/election_liberal_events
election_events/election_moderate_events
election_events/election_neutral_events
election_events/election_other_parties_events
law_events/anti_state_religion_law_events
law_events/bureaucracy
law_events/children_rights_events
law_events/citizenship_laws
law_events/conscription_laws
law_events/council_republic_law_events
law_events/distribution_of_power_laws
law_events/economy_laws
law_events/education_laws
law_events/free_speech_laws
law_events/healthcare_laws
law_events/internal_security_events
law_events/isolationism_law
law_events/labor_rights_laws
law_events/law_events
law_events/laws
law_events/laws_police
law_events/migration_laws
law_events/monarchy_laws
law_events/republic_laws
law_events/rights_of_women_laws
law_events/single_party_state_laws
law_events/tax_laws
law_events/technocracy_law
law_events/theocracy
law_events/welfare_laws_events
""".split()

# Files where CWP 1.5 used only some of the events (the rest are 1836-era or need content CWP does not have;
# internal_security_events.4-6 need the Guaranteed Liberties law)
KEEP = {
    "agitators_events/revolution_events_02": ["revolution_pulse_events.%d" % i for i in range(1, 41) if i != 6],
    "autocracy_events": ['autocracy.2', 'autocracy.3'],
    "commander_events": ['commander_events.2', 'commander_events.4', 'commander_events.6'],
    "communism": ['communism.7'],
    "crime_events": ['crime_events.1', 'crime_events.2'],
    "decree_events_02": ['decree_events.100', 'decree_events.101', 'decree_events.102', 'decree_events.103', 'decree_events.104', 'decree_events.105', 'decree_events.106', 'decree_events.108', 'decree_events.109'],
    "diplomatic_friction_events": ['diplomatic_friction.1', 'diplomatic_friction.2', 'diplomatic_friction.3'],
    "fascism_events": ['fascism_events.8'],
    "ig_petitions": ['ig_petitions.1', 'ig_petitions.4', 'ig_petitions.7', 'ig_petitions.13', 'ig_petitions.16', 'ig_petitions.22'],
    "psychology_events": ['psychology_events.1', 'psychology_events.2', 'psychology_events.3', 'psychology_events.4'],
    "election_events/election_other_parties_events": ['election_other_parties_events.1', 'election_other_parties_events.2', 'election_other_parties_events.4', 'election_other_parties_events.5'],
    "law_events/internal_security_events": ['internal_security_events.1', 'internal_security_events.2', 'internal_security_events.3'],
    "law_events/labor_rights_laws": ['labor_rights.1', 'labor_rights.4', 'labor_rights.5', 'labor_rights.6'],
    "law_events/technocracy_law": ['technocracy.1', 'technocracy.2', 'technocracy.3'],
}
# Events CWP keeps in its own files, in the form CWP 1.5 had, because the base game rebuilt them around content CWP
# does not have; they stay in the restored hooks. The Red Army (communism.8) needs the Revolutionary Guard law and the
# militant, disciplinarian and internationalist ideologies since 1.15.
PINNED = {"communism.8": "events/cwp_red_army_event.txt"}

# Vanilla buildings CWP replaced (dev's own mapping in the disabled .info copies); None = no CWP equivalent
BUILDINGS = {
    "building_arms_industry": "building_small_arms_manufactories",
    "building_art_academy": "building_university",
    "building_chemical_plant": "building_chemical_plants",
    "building_explosives_factory": "building_explosives_industry",
    "building_furniture_manufactory": "building_furniture_manufactories",
    "building_gold_field": "building_gold_mine",
    "building_paper_mill": "building_paper_manufactories",
    "building_steel_mill": "building_steelworks",
    "building_textile_mill": "building_textile_manufactories",
    "building_tooling_workshop": "building_tool_manufactories",
    "building_whaling_station": "building_fishing_wharf",
    "building_automotive_industry": "building_automobile_manufactories",
    "building_electrics_industry": "building_electronic_components_manufactories",
    "building_munition_plant": "building_munitions_plants",
    "building_dye_plantation": None,
    "building_opium_plantation": None,
    "building_silk_plantation": None,
    "building_rubber_plantation": None,
}
# 19th-century technologies every 1946 country has (CWP's tree starts after them)
OLD_TECHS = set("""bolt_action_rifles egalitarianism handcranked_machine_gun intensive_agriculture labor_movement
mass_communication mass_propaganda military_statistics modern_nursing modern_sewerage nco_training
philosophical_pragmatism political_agitation psychiatry psychoanalysis railways repeaters socialism stormtroopers
trench_works wargaming""".split())



def blocks(text):
    """Top-level `key = { ... }` blocks: (key, start, end) with end after the closing brace."""
    out = []
    i, n = 0, len(text)
    depth = 0
    start = key = None
    while i < n:
        c = text[i]
        if c == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == '"':
            j = text.find('"', i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == "{":
            if depth == 0:
                m = re.search(r"([A-Za-z_0-9.:@]+)\s*=\s*$", text[max(0, i - 200):i])
                key = m.group(1) if m else None
                ls = text.rfind("\n", 0, i) + 1
                start = ls
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                out.append((key, start, i + 1))
                start = None
        i += 1
    return out


def event_ids(text):
    return [k for k, s, e in blocks(text) if k and re.fullmatch(r"[a-z_0-9]+\.\d+", k)]


def trim(text, keep):
    """Drop top-level event blocks whose id is not in keep (with the comment lines right above them)."""
    bl = blocks(text)
    cut = []
    for k, s, e in bl:
        if k and re.fullmatch(r"[a-z_0-9]+\.\d+", k) and k not in keep:
            # extend start upwards over directly preceding comment lines
            s2 = s
            while True:
                prev = text.rfind("\n", 0, s2 - 1) + 1
                line = text[prev:s2].strip()
                if s2 > 0 and line.startswith("#"):
                    s2 = prev
                else:
                    break
            cut.append((s2, e))
    for s, e in reversed(cut):
        text = text[:s] + text[e:]
    return re.sub(r"\n{3,}", "\n\n", text)


def enclosing_key(text, pos):
    depth = 0
    i = pos
    while i > 0:
        i -= 1
        c = text[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                m = re.search(r"([A-Za-z_0-9.:@?]+)\s*=\s*$", text[max(0, i - 120):i])
                return m.group(1) if m else ""
            depth -= 1
    return ""


def adapt(text, rel):
    notes = []
    # buildings
    for old, new in BUILDINGS.items():
        if old not in text:
            continue
        if new:
            if old == "building_power_plant":
                continue
            text = re.sub(r"\b%s\b" % old, new, text)
        else:
            text = re.sub(r"(?m)^[ \t]*is_building_type = %s[ \t]*(#[^\n]*)?\r?\n" % old, "", text)
        notes.append(old)
    if "is_building_type = building_power_plant" in text:
        text = re.sub(r"(?m)^([ \t]*)is_building_type = building_power_plant\b",
                      r"\1is_building_type = building_combustion_plant\n\1is_building_type = building_nuclear_power_plant", text)
    # technologies known by 1946
    for m in reversed(list(re.finditer(r"NOT\s*=\s*\{\s*has_technology_researched\s*=\s*([a-z_]+)\s*\}", text))):
        if m.group(1) in OLD_TECHS:
            text = text[:m.start()] + "always = no" + text[m.end():]
    for m in reversed(list(re.finditer(r"(?m)^([ \t]*)has_technology_researched\s*=\s*([a-z_]+)[ \t]*(#[^\n]*)?(\r?\n)", text))):
        if m.group(2) in OLD_TECHS:
            if enclosing_key(text, m.start()) in ("OR", "NOR"):
                text = text[:m.start()] + m.group(1) + "always = yes" + m.group(4) + text[m.end():]
            else:
                text = text[:m.start()] + text[m.end():]
    return text, notes


def outer_block(text, pos, key):
    """(start, end) of the innermost block named key that encloses pos (start = start of its line)."""
    depth = 0
    i = pos
    while i > 0:
        i -= 1
        c = text[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                m = re.search(r"([A-Za-z_0-9.:@?]+)\s*=\s*$", text[max(0, i - 120):i])
                if m and m.group(1) == key:
                    j, d = i + 1, 1
                    while d:
                        d += {"{": 1, "}": -1}.get(text[j], 0)
                        j += 1
                    return text.rfind("\n", 0, i) + 1, j
            else:
                depth -= 1
    return None



# The base game's parties CWP 1.5 does not have, and the CWP 1.5 party (common/parties/cwp_*_party.txt) taking their place
# in these events, as CWP 1.5 adapted them: the free trade campaign is the liberals', the hawks' the conservatives', the
# radicals' the social democrats'
PARTIES = {"free_trade_party": "liberal_party", "military_party": "conservative_party", "radical_party": "social_democrat_party",
           "religious_party": "christian_democrat_party", "revolutionary_party": "socialist_party"}


def fixes(text, c):
    # the fringe parties gaining from the moderates' troubles: CWP 1.5 has the democratic socialists in the radicals' place
    if c == "election_events/election_moderate_events":
        text = text.replace("py:radical_party", "py:democratic_socialist_party")
    text = re.sub(r"\b(is_party_type = |py:)(%s)\b" % "|".join(PARTIES), lambda m: m.group(1) + PARTIES[m.group(2)], text)
    # the base game's fallbacks between those parties and the ones CWP 1.5 folds them into
    text = re.sub(r"OR = \{\s*(is_party_type = [a-z_]+)\s*\1\s*\}", r"\1", text)
    text = re.sub(r"(NOT = \{ is_party_type = [a-z_]+ \})\s*\1", r"\1", text)
    text = re.sub(r"if = \{\s*limit = \{ exists = (py:[a-z_]+) \}\s*\1 = \{ save_scope_as = ([a-z_]+) \}\s*\}\s*"
                  r"else = \{\s*\1 = \{ save_scope_as = \2 \}\s*\}", r"\1 = { save_scope_as = \2 }", text)
    text = re.sub(r"(?m)^[ \t]*has_trait = opium_addiction[ \t]*\n", "", text)
    text = re.sub(r"(?m)^[ \t]*has_ideology = ideology:ideology_egalitarian_modern[ \t]*\n", "", text)
    text = re.sub(r"\n[ \t]*if = \{\s*limit = \{\s*owner = \{\s*c:FRA \?= this\s*has_journal_entry = je_divided_monarchists\s*\}\s*\}\s*"
                  r"fra_disfavor_leader_ig_dynasty = yes\s*\}", "", text)
    text = re.sub(r"\n[ \t]*NOT = \{\s*has_active_production_method = pm_tools_disabled\s*\}", "", text)
    text = re.sub(r"\n[ \t]*NOT = \{\s*has_law = law_type:law_bakufu\s*\}", "", text)
    text = re.sub(r"\n[ \t]*OR = \{\s*has_active_production_method = pm_philosophy_department\s*"
                  r"has_active_production_method = pm_analytical_philosophy_department\s*\}", "", text)
    text = re.sub(r"(?m)^[ \t]*has_active_production_method = pm_philosophy_department[ \t]*\n", "", text)
    text = re.sub(r"(?m)^[ \t]*(NOT = \{ )?has_law_or_variant = law_type:law_guaranteed_liberties( \})?[ \t]*\n", "", text)
    # fish is not a CWP good
    text = re.sub(r"\n[ \t]*mg:fish = \{\s*market_goods_pricier > 0\.25\s*\}", "", text)
    text = re.sub(r"\n[ \t]*else_if = \{\s*limit = \{\s*market_capital\.market = \{\s*\}\s*\}\s*g:fish = \{\s*save_scope_as = [a-z_]+\s*\}\s*\}", "", text)
    # vanilla bug: the rival-country fallbacks are `else_if` blocks without a limit, so only the first can run
    if c == "fascism_events":
        def add_limit(m):
            ind, cond = m.group(1), m.group(3)
            lines = [l.strip() for l in cond.strip().split("\n") if l.strip()]
            lim = (ind + "\tlimit = {\n" + ind + "\t\tany_country = {\n"
                   + "".join(ind + "\t\t\t" + l + "\n" for l in lines) + ind + "\t\t}\n" + ind + "\t}\n")
            return "\n" + ind + "else_if = {\n" + lim + m.group(2)
        text = re.sub(r"\n([ \t]*)else_if = \{\n(\s*random_country = \{\s*limit = \{(.*?)\}\s*save_scope_as = rival_country)",
                      add_limit, text, flags=re.S)
    # vanilla bug: the neighbour's state can change hands (occupation zones merge) before the event is answered
    if c == "neighbor_events":
        text = re.sub(r"scope:(neighbor_state|neighbor_neighbor_state|neighbor_country) = \{", r"scope:\1 ?= {", text)
    # vanilla bug: the agitator law events save the government IG and its leader, and the IGs in government for and
    # against the law, only when there is one
    if c == "agitators_events/agitator_law_events_2":
        text = re.sub(r"scope:(govnas|da_boss|governing_ig|opposing_ig|supporting_ig) = \{", r"scope:\1 ?= {", text)
    if c == "agitators_events/agitators_law_events":
        text = re.sub(r"scope:supporting_ig = \{", r"scope:supporting_ig ?= {", text)
    # vanilla bug: revolution_pulse_events.13 fires at medium progress but saves its scopes from a low progress revolution
    if c == "agitators_events/revolution_events_02":
        k = text.find("revolution_pulse_events.13 = {")
        i = text.find("\timmediate = {", k)
        j = text.find("civil_war_progress_low = yes", i)
        if k >= 0 and 0 <= i < j < text.find("\toption = {", i):
            text = text[:j] + "civil_war_progress_medium = yes" + text[j + len("civil_war_progress_low = yes"):]
    # CWP has no prohibition laws: drop the organised crime event's tie-in with them
    if c == "crime_events":
        text = re.sub(r"\n[ \t]*if = \{\s*limit = \{\s*has_variable = prohibition_laws_var\s*\}\s*custom_tooltip = [A-Za-z_.]+\s*"
                      r"change_variable = \{\s*name = prohibition_laws_var\s*add = -?\d+\s*\}\s*\}", "", text)
    # CWP has no Krakatoa events: drop the natural disasters' check for their crop failure
    if c == "natural_disasters_events":
        text = re.sub(r"(?m)^[ \t]*NOT = \{ has_variable = krakatoa_crop_failure \}[ \t]*\r?\n", "", text)
    # vanilla bug: the mega disaster counters test a country variable, so they never count past 1
    text = re.sub(r"exists = var:(number_of_mega_[a-z]+)", r"has_global_variable = \1", text)
    # CWP's war pace: war support changes at 7/21 of the base game's rate, so thresholds on its change scale with it
    if c == "election_events/election_contextual_events":
        text = re.sub(r"(has_war_support_change = \{\s*target = ROOT\s*value < )-5\n",
                      r"\1-1.67 # vanilla -5 at CWP's war pace (cwp_war_support_pace in common/script_values/cwp_war_values.txt)\n",
                      text)
    # vanilla bugs: `ruler` evaluated in interest group scope; the ruling party compared with the party of interest
    # groups that have none; a trigger's temporary scope used in immediate
    if c == "law_events/single_party_state_laws":
        text = text.replace("this = ruler.interest_group", "this = ROOT.ruler.interest_group")
        text = text.replace("this.party = ruler.interest_group.party",
                            "AND = { has_party = yes this.party = ROOT.ruler.interest_group.party }")
    if c == "law_events/distribution_of_power_laws":
        k = text.find("save_scope_as = universal_voting_ig")
        if k >= 0:
            j = text.find("scope:universal_suffrage_ig ?= this", k)
            if j >= 0:
                text = text[:j] + "scope:universal_voting_ig ?= this" + text[j + len("scope:universal_suffrage_ig ?= this"):]
    # David Copperfield is a British character template CWP does not have: everyone gets the generic politician
    k = text.find("template = GBR_david_copperfield")
    if k >= 0:
        s, e = outer_block(text, k, "if")
        m = re.match(r"\s*else = \{", text[e:])
        es, ee = e + m.end() - 1, None
        d, j = 0, es
        while True:
            d += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
            if d == 0:
                ee = j
                break
        body = text[es + 1:ee - 1].strip("\n")
        body = "\n".join(l[1:] if l.startswith("\t") else l for l in body.split("\n"))
        text = text[:s] + body.rstrip() + "\n" + text[ee:].lstrip(" \t").lstrip("\n")
    return text


# The base game's State and Revolution content (Victoria 3 1.15: tsarpoints, Russian and Polish AI, the Russian civil
# war, ...) and its 1836 France (the divided monarchists' AI and the French royal houses) are not part of CWP. Their
# journal entries, variables and AI triggers never exist in a CWP game, so a check for them is always false: the
# statements are replaced with `always = no` (`always = yes` for `= no`), which keeps every block's structure and meaning
SR_HOOK = (r"(?:je_tp_\w+|\w*tsarpoints\w*|ai_russia_\w+|je_russia_\w+|\w*congress_poland\w*|ai_poland_\w+|rcw_\w+|rlit_\w+"
           r"|nemo_\w+|je_state_and_revolution|divided_monarchists_\w+|character_is_french_house|character_is_rival_french_house"
           r"|character_matches_divided_monarchists_ai_path)")


def drop_state_and_revolution(text):
    text = re.sub(r"(?m)^([ \t]*)(?:has_journal_entry|has_variable|has_global_variable)\s*=\s*%s[ \t]*(#[^\n]*)?$" % SR_HOOK,
                  r"\1always = no", text)
    text = re.sub(r"(?<=\{ )(?:has_journal_entry|has_variable|has_global_variable)\s*=\s*%s(?= \})" % SR_HOOK, "always = no", text)
    text = re.sub(r"(?m)^([ \t]*)%s\s*=\s*yes[ \t]*(#[^\n]*)?$" % SR_HOOK, r"\1always = no", text)
    text = re.sub(r"(?m)^([ \t]*)%s\s*=\s*no[ \t]*(#[^\n]*)?$" % SR_HOOK, r"\1always = yes", text)
    return text


# The base game's 1.15 ideologies that replaced ones CWP keeps (CWP's ideologies are 1.14's): its communist and state
# socialist leader ideologies are CWP's communist and social democrat ones, the Patriotic ideology it split is CWP's
# patriotic, and the Red Army's new militant, disciplinarian and internationalist ideologies stand for the proletarian
# ideology the Red Army took in 1.14
IDEOLOGY_RENAMES = {"ideology_communist_leader": "ideology_communist", "ideology_state_socialist": "ideology_social_democrat",
                    "ideology_militarist": "ideology_patriotic", "ideology_militant": "ideology_proletarian",
                    "ideology_disciplinarian": "ideology_proletarian", "ideology_internationalist": "ideology_proletarian"}
_KNOWN = {}


def known(folder):
    """Keys CWP defines in common/<folder> (placeholders excluded)."""
    if folder not in _KNOWN:
        ks = set()
        for p in glob.glob(os.path.join(TARGET, "common", folder, "**", "*.txt"), recursive=True):
            t = open(p, encoding="utf-8-sig", errors="replace").read()
            if not t.startswith("# CWP placeholder"):
                ks.update(k for k, s, e in blocks(t) if k)
        _KNOWN[folder] = ks
    return _KNOWN[folder]


def neutralize_unknown(text):
    """Base-game ideologies, traits, laws, journal entries and character templates CWP does not have never exist in a CWP
    game: a check for one is false (`always = no`), and an effect adding or removing one is dropped."""
    for old, new in IDEOLOGY_RENAMES.items():
        text = re.sub(r"\b%s\b" % old, new, text)
    checks = (("ideologies", r"has_ideology\s*=\s*ideology:(\w+)"), ("character_traits", r"has_trait\s*=\s*(\w+)"),
              ("laws", r"(?:has_law(?:_or_variant)?|is_enacting_law)\s*=\s*law_type:(\w+)"), ("journal_entries", r"has_journal_entry\s*=\s*(\w+)"),
              ("character_templates", r"has_template\s*=\s*(\w+)"))
    for folder, rx in checks:
        ks = known(folder)
        text = re.sub(rx, lambda m: m.group(0) if m.group(1) in ks else "always = no", text)
    for folder, rx in (("ideologies", r"(?:add|remove)_ideology\s*=\s*(\w+)"), ("character_traits", r"(?:add|remove)_trait\s*=\s*(\w+)")):
        ks = known(folder)
        text = re.sub(r"(?m)^[ \t]*%s[ \t]*(#[^\n]*)?\n" % rx, lambda m: m.group(0) if m.group(1) in ks else "", text)
    return text


def vanilla_defs(folder):
    defs = {}
    for p in sorted(glob.glob(os.path.join(V14, "common", folder, "*.txt"))):
        t = open(p, encoding="utf-8-sig").read().replace("\r\n", "\n")
        for k, s, e in blocks(t):
            if k and k not in defs:
                defs[k] = (os.path.basename(p), t[s:e])
        if folder == "script_values":  # plain `name = 50` values
            for m in re.finditer(r"(?m)^([a-z_0-9]+)\s*=\s*(-?[0-9.]+|[a-z_0-9]+)[ \t]*(#[^\n]*)?$", t):
                defs.setdefault(m.group(1), (os.path.basename(p), m.group(0)))
    return defs


def mod_defs(folder):
    ks = set()
    for p in glob.glob(os.path.join(TARGET, "common", folder, "**", "*.txt"), recursive=True):
        if os.path.basename(p).startswith("cwp_vanilla_event"):
            continue
        t = open(p, encoding="utf-8-sig", errors="replace").read()
        ks.update(k for k, s, e in blocks(t) if k)
        if folder == "script_values":
            ks.update(re.findall(r"(?m)^\ufeff?([a-z_0-9]+)\s*=\s*[^{\s]", t))
    return ks


BUILDING_GROUPS = {"bg_whaling": "bg_fishing", "bg_oil_extraction": "bg_oil_rig"}


def support_fix(folder, body):
    if folder == "static_modifiers":
        for old, new in BUILDINGS.items():
            if new:
                body = body.replace(old + "_", new + "_")
        for old, new in BUILDING_GROUPS.items():
            body = body.replace("building_group_%s_" % old, "building_group_%s_" % new)
    if folder == "scripted_triggers":
        # Japan's sakoku and hierarchic ideologies and the corporate state are not in CWP
        body = re.sub(r"(?m)^[ \t]*[^\n]*(law_type:law_sakoku|law_type:law_corporate_state|ideology:ideology_japan_hierarchic[_0-9]*|character_role_emperor_of_japan)\b[^\n]*\n", "", body)
        # nor are the State and Revolution decree variants (1.15)
        body = re.sub(r"(?m)^[ \t]*has_decree = \$DECREE\$_tsarpoints[ \t]*\n", "", body)
        body = re.sub(r"OR = \{\s*\n([ \t]*)([^\n{}]+)\n\s*\}", lambda m: m.group(2).strip(), body)
    body = drop_state_and_revolution(body)
    if folder in ("scripted_triggers", "scripted_effects"):
        body = neutralize_unknown(body)
    return body


def write_support(folder, fname, names, title):
    vd = vanilla_defs(folder)
    have = mod_defs(folder)
    by_file = {}
    missing = []
    for n in sorted(names):
        if n in have:
            continue
        if n not in vd:
            missing.append(n)
            continue
        by_file.setdefault(vd[n][0], []).append(support_fix(folder, vd[n][1]))
    out = ["# CWP: %s from the base game's %s, needed by the restored vanilla flavour events" % (title, folder),
           "# (the mod blanks the vanilla files of this folder). Generated by docs/maintenance/restore_flavour_events.py.", ""]
    for f in sorted(by_file):
        out.append("# from %s" % f)
        out.extend(b.rstrip() + "\n" for b in by_file[f])
    path = os.path.join(TARGET, "common", folder, fname)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write("\n".join(out))
    return sum(len(v) for v in by_file.values()), missing


def referenced(texts):
    mods, trig, eff, vals = set(), set(), set(), set()
    for t in texts:
        t = re.sub(r"#[^\n]*", "", t)
        mods.update(re.findall(r"\bname\s*=\s*([A-Za-z_0-9]+)", t))
        mods.update(re.findall(r"\b(?:has_modifier|remove_modifier)\s*=\s*([A-Za-z_0-9]+)", t))
        for k in re.findall(r"\b([a-z_0-9]+)\s*=\s*(?:yes|no)\b", t):
            trig.add(k)
            eff.add(k)
        for k in re.findall(r"\b([a-z_0-9]+)\s*=\s*\{", t):
            trig.add(k)
            eff.add(k)
        vals.update(re.findall(r"[<>=]=?\s*([a-z][a-z_0-9]+)\b", t))
        vals.update(re.findall(r"\b(?:value|add|multiply|subtract|divide|days|months|years)\s*=\s*([a-z][a-z_0-9]+)\b", t))
    return mods, trig, eff, vals


HOOKS = [  # (CWP named on_action, vanilla file, vanilla on_action, caller in 00_code_on_actions.txt, comment)
    ("cwp_flavour_yearly_events", "00_on_actions_yearly.txt", "on_yearly_events", "on_yearly_pulse_country",
     "Yearly flavour events (government conflicts, neighbours, decrees, disasters, ...)"),
    ("cwp_flavour_exiles_yearly_events", "00_on_actions_yearly.txt", "exiles_yearly_events", "on_yearly_pulse_country",
     "Yearly exile events"),
    ("cwp_flavour_monthly_events", "00_code_on_actions.txt", "on_monthly_pulse_country", "on_monthly_pulse_country",
     "Monthly checks (Red Army rename, exiled agitators)"),
    ("cwp_flavour_election_events", "00_on_actions_election.txt", "elections_monthly_events", "on_monthly_pulse_country_elections",
     "Election campaign events"),
    ("cwp_flavour_five_year_events", "00_code_on_actions.txt", "on_five_year_pulse_country", "on_five_year_pulse_country",
     "Five-yearly events"),
    ("cwp_flavour_law_checkpoint_advance", "00_code_on_actions.txt", "on_law_checkpoint_advance", "on_law_checkpoint_advance",
     "Law enactment: checkpoint advanced"),
    ("cwp_flavour_law_checkpoint_debate", "00_code_on_actions.txt", "on_law_checkpoint_debate", "on_law_checkpoint_debate",
     "Law enactment: debate"),
    ("cwp_flavour_law_checkpoint_stall", "00_code_on_actions.txt", "on_law_checkpoint_stall", "on_law_checkpoint_stall",
     "Law enactment: stalled"),
    ("cwp_flavour_revolution_checkpoint", "00_code_on_actions.txt", "on_revolution_checkpoint_reached", "on_revolution_checkpoint_reached",
     "Revolution checkpoints"),
    ("cwp_flavour_secession_checkpoint", "00_code_on_actions.txt", "on_secession_checkpoint_reached", "on_secession_checkpoint_reached",
     "Secession checkpoints"),
]
# CWP 1.5's own changes to vanilla's pools
WEIGHTS = {"prostitution.2": 20, "natural_disaster_events.5": 3}
EXTRA = {"cwp_flavour_law_checkpoint_stall": [(10, "agitators_law_events.3")]}


def named_block(text, name):
    for k, s, e in blocks(text):
        if k == name:
            return text[s:e]
    return None



def hooked_ids():
    ids = set()
    for p in glob.glob(os.path.join(TARGET, "common", "on_actions", "*.txt")):
        if os.path.basename(p) == "cwp_flavour_events_on_actions.txt":
            continue
        t = re.sub(r"#[^\n]*", "", open(p, encoding="utf-8-sig", errors="replace").read())
        ids.update(re.findall(r"\b([a-z_0-9]+\.\d+)\b", t))
    return ids



def write_hooks(restored):
    allowed = restored - hooked_ids()  # events the mod's own on_actions fire stay there (generic law events, ...)
    out = ["# CWP: the base game's hooks for the restored flavour events (docs/maintenance/restore_flavour_events.py), limited to the",
           "# events CWP 1.5 used. Called from common/on_actions/00_code_on_actions.txt. Generated; do not edit by hand.", ""]
    stats = {}
    for name, vfile, vname, caller, comment in HOOKS:
        vt = open(os.path.join(V14, "common", "on_actions", vfile), encoding="utf-8-sig").read().replace("\r\n", "\n")
        body = named_block(vt, vname)
        lines = [f"# {comment}", name + " = {"]
        n = 0
        ev = re.search(r"\bevents\s*=\s*\{([^}]*)\}", body)
        rb = re.search(r"random_events\s*=\s*\{", body)
        if rb:
            j, d = rb.end(), 1
            while d:
                d += {"{": 1, "}": -1}.get(body[j], 0)
                j += 1
            inner = re.sub(r"#[^\n]*", "", body[rb.end():j - 1])
            lines.append("\trandom_events = {")
            m = re.search(r"chance_to_happen\s*=\s*(\d+)", inner)
            if m:
                lines.append("\t\tchance_to_happen = " + m.group(1))
            for w, e in re.findall(r"(?m)^\s*(\d+)\s*=\s*([a-z_0-9.]+)\s*$", inner):
                if e == "0":
                    lines.append(f"\t\t{w} = 0")
                elif e in allowed:
                    lines.append(f"\t\t{WEIGHTS.get(e, int(w))} = {e}")
                    n += 1
            for w, e in EXTRA.get(name, []):
                if e in allowed and f"= {e}" not in "\n".join(lines):
                    lines.append(f"\t\t{w} = {e}")
                    n += 1
            lines.append("\t}")
        if ev:
            keep = [e for e in re.findall(r"\b([a-z_0-9]+\.\d+)\b", re.sub(r"#[^\n]*", "", ev.group(1))) if e in allowed]
            if keep:
                lines.append("\tevents = {")
                lines += ["\t\t" + e for e in keep]
                lines.append("\t}")
                n += len(keep)
        lines.append("}")
        stats[name] = n
        out += lines + [""]
    with open(os.path.join(TARGET, "common", "on_actions", "cwp_flavour_events_on_actions.txt"), "w",
              encoding="utf-8-sig", newline="\r\n") as f:
        f.write("\n".join(out))
    return stats


def patch_code_on_actions():
    p = os.path.join(TARGET, "common", "on_actions", "00_code_on_actions.txt")
    t = open(p, encoding="utf-8-sig").read().replace("\r\n", "\n")
    for name, vfile, vname, caller, comment in HOOKS:
        bl = [(s, e) for k, s, e in blocks(t) if k == caller]
        s, e = bl[0]
        b = t[s:e]
        if name in b:
            continue
        # drop dev's commented-out vanilla event lists
        b = re.sub(r"\n(?:[ \t]*\n)*[ \t]*random_events = \{[^{}]*\}", lambda m: "" if not re.search(r"(?m)^\s*\d+\s*=\s*[a-z_0-9]+\.\d+", re.sub(r"#[^\n]*", "", m.group(0))) else m.group(0), b)
        m = re.search(r"\n([ \t]*)on_actions = \{", b)
        if m:
            j, d = m.end(), 1
            while d:
                d += {"{": 1, "}": -1}.get(b[j], 0)
                j += 1
            close = b.rfind("}", 0, j)
            ind = m.group(1)
            extra = ("%s\tdelay = { days = 5 }\n" % ind if name == "cwp_flavour_exiles_yearly_events" else "")
            b = b[:close].rstrip() + "\n" + extra + ind + "\t" + name + "\t# " + comment + "\n" + ind + b[close:]
        else:
            close = b.rfind("}")
            b = b[:close].rstrip() + "\n\n\ton_actions = {\n\t\t" + name + "\t# " + comment + "\n\t}\n" + b[close:]
        t = t[:s] + b + t[e:]
    with open(p, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(t)


def main():
    trimmed = {}
    written = []
    for c in CANDS:
        rel = "events/" + c + ".txt"
        src = os.path.join(V14, "events", c.replace("/", os.sep) + ".txt")
        text = open(src, encoding="utf-8-sig").read().replace("\r\n", "\n")
        ids = set(event_ids(text))
        extra = ids - set(KEEP[c]) if c in KEEP else set()
        if extra:
            text = trim(text, set(KEEP[c]))
            trimmed[c] = sorted(extra)
        text, notes = adapt(text, rel)
        text = fixes(text, c)
        text = drop_state_and_revolution(text)
        text = neutralize_unknown(text)
        header = "# CWP: the base game's %s flavour events, restored because CWP 1.5 had them" % ("/".join(c.split("/")[:-1]) or "general")
        if extra:
            header += "\n# (only the events CWP 1.5 used)"
        header += ". Adapted to CWP's buildings, laws and the 1946\n# technology level by docs/maintenance/restore_flavour_events.py; rerun it after game updates.\n"
        out = header + text
        written.append(out)
        dst = os.path.join(TARGET, "events", c.replace("/", os.sep) + ".txt")
        with open(dst, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(out)
    print("written", len(CANDS), "event files; trimmed:", {k: len(v) for k, v in trimmed.items()})
    # support definitions, iterated so that definitions pulled in can pull in their own dependencies
    texts = list(written)
    for _ in range(4):
        mods, trig, eff, vals = referenced(texts)
        n1, m1 = write_support("static_modifiers", "cwp_vanilla_event_modifiers.txt", mods & set(vanilla_defs("static_modifiers")), "event modifiers")
        n2, m2 = write_support("scripted_triggers", "cwp_vanilla_event_triggers.txt", trig & set(vanilla_defs("scripted_triggers")), "scripted triggers")
        n3, m3 = write_support("scripted_effects", "cwp_vanilla_event_effects.txt", eff & set(vanilla_defs("scripted_effects")), "scripted effects")
        n4, m4 = write_support("script_values", "cwp_vanilla_event_values.txt", vals & set(vanilla_defs("script_values")), "script values")
        new_texts = list(written)
        for f in ("static_modifiers/cwp_vanilla_event_modifiers.txt", "scripted_triggers/cwp_vanilla_event_triggers.txt",
                  "scripted_effects/cwp_vanilla_event_effects.txt", "script_values/cwp_vanilla_event_values.txt"):
            new_texts.append(open(os.path.join(TARGET, "common", f.replace("/", os.sep)), encoding="utf-8-sig").read())
        if [len(x) for x in new_texts] == [len(x) for x in texts]:
            break
        texts = new_texts
    print("support: modifiers", n1, "triggers", n2, "effects", n3, "values", n4)
    restored = set(PINNED)
    for x in written:
        restored.update(event_ids(x))
    print("hooks:", write_hooks(restored))
    patch_code_on_actions()


if __name__ == "__main__":
    main()
