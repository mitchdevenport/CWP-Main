"""Fit the 1946 institutions to what each country's budget and bureaucracy can run.

The 1946 law packages (common/scripted_effects/cwp_starting_law_packages.txt) start most countries with a dozen
institutions at levels 2-5, where CWP 1.5 started almost every country without any (nine country histories set some,
all at low levels). With the generated building history's administrations they ruined the AI's budgets in 1946-1955
tests (69 bankruptcies by 1955, against 23 in CWP 1.5):

- Social security: each level raises the wage every pop in the workforce is topped up to by a fifth of the normal
  wage, so level 5 pays every unemployed or poorly paid worker up to a full normal wage. World welfare payments were
  23% of all government income in February 1946 (CWP 1.5: about 1%); Britain paid a million a week, Yugoslavia and
  Bulgaria more than their whole income. This lowers each country's social security to the highest level whose
  payments stay within a tenth of its income; where even level 1 (the lowest an institution runs at while its law
  stands) would pay more, the country starts without social security (law_no_social_security), as almost every
  country did in CWP 1.5.

- Administrations: the generated building history gave many countries several times CWP 1.5's administrations (Poland
  212 levels against 60, Hungary 61 against 7, South Korea 228 against 30), at about 1,000 a level a week (filing systems
  and mail couriers use 10 paper a level), so that Poland, Hungary, North Korea and Bulgaria spent one to three times
  their whole income on them. The AI cut them back to about CWP 1.5's levels by 1955, but went bankrupt doing so.
  Where a country's administrations cost more than 30% of its income and their bureaucracy is not all needed, this
  trims them to what 30% of the income pays for, never below every state's tax capacity (a point per 10,000 pops
  above the state's own 100, 50 a level) nor below what the country's institutions need at level 1, taking the cut
  from each state in proportion to its levels above that state's need; the institutions are then fitted to the
  remaining bureaucracy as below.

- Bureaucracy: each institution level costs about 10.5 bureaucracy per million people, and a country whose usage is
  twice its bureaucracy or more wastes all of its taxes and government dividends (vanilla 1.14's bureaucracy deficit).
  42 countries started in deficit and 23 of them, Switzerland, Norway, the Netherlands, Romania and Chile among them,
  collected no taxes at all. For every country whose bureaucracy usage (after the social security cut) is above its
  generation / 1.10, this scales its institution levels by the same factor (each keeps at least level 1; the cost is
  linear in the levels) so that usage fits, and where even level 1 everywhere is too much, adds administration levels
  (filing systems, 150 bureaucracy a level) to the country's states by population - except for countries whose
  administrations were less than 80% staffed, as 1.14 hires clerks only in proportion to the bureaucrats a building
  finds (India's 400 levels were 13% staffed in 1946, and more levels would not have been staffed either; new
  administrations of countries that had none were staffed).

The AI raises the institutions again as its budget and bureaucracy allow.

Input: an observer game's debug.log with this probe (one line per country and month, January to June 1946):

    on_monthly_pulse_country = { on_actions = { cwp_probe_bur } }
    cwp_probe_bur = {
        trigger = { game_date < 1946.7.2 }
        effect = { debug_log = "CWPPROBE BUR [TimeKeeper.GetCurrentDate.GetString] [THIS.GetCountry.GetTagName] x
            bal=[THIS.GetCountry.MakeScope.ScriptValue('cwp_probe_bur_balance')|0] x
            use=[THIS.GetCountry.MakeScope.ScriptValue('cwp_probe_bur_usage')|0] x
            inst=[THIS.GetCountry.GetInstitutionInvestmentBureaucracyCost|0] x
            wel=[THIS.GetCountry.GetWelfarePaymentsExpenses|0] inc=[THIS.GetCountry.PredictWeeklyIncome|0]" }
    }
    # script values: cwp_probe_bur_balance = { value = bureaucracy }  cwp_probe_bur_usage = { value = bureaucracy_usage }

(the x stands for the rest of the line), run on the mod WITHOUT common/history/global/cwp_starting_institutions.txt and
common/history/buildings/cwp_starting_administrations.txt and with the history buildings this script has not yet
edited, and a save from February 1946 of that game (for the starting institution levels and populations).

usage: python docs/maintenance/fit_starting_institutions.py <debug.log> <save.v3> [--write]
"""
import argparse
import collections
import math
import os
import re

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPARE = 1.10                # generation kept above usage (throughput moves it by up to a tenth)
ADMIN_PER_LEVEL = 150       # pm_filing_systems: country_bureaucracy_add (workforce scaled)
MIN_STAFFING = 0.8          # administrations are added only where the existing ones were this staffed
WELFARE_SHARE = 0.10        # welfare payments kept within this share of the weekly income
ADMIN_SHARE = 0.30          # administrations kept within this share of the weekly income where their bureaucracy is spare
GEN_BASE = 100              # bureaucracy a country generates without administrations
STATE_TAX_CAPACITY = 100    # every state's own tax capacity; taxing takes a point per 10,000 pops
CAPACITY_PER_LEVEL = 50     # pm_filing_systems: state_tax_capacity_add (workforce scaled)
SOCIAL_SECURITY = "institution_social_security"
OUT = os.path.join("common", "history", "global", "cwp_starting_institutions.txt")
NEW_ADMIN = os.path.join("common", "history", "buildings", "cwp_starting_administrations.txt")


def probe_lines(path):
    """Best (most staffed) generation of January-June 1946 per country, with the usage at that time; and the median
    welfare payments and income of February-June (January's are still settling, and a month's predicted income can
    jump to twenty times the usual, as Denmark's did)."""
    best = {}
    money = collections.defaultdict(list)
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"CWPPROBE BUR (\w+) \d+, 1946 (\w+) .*?bal=(-?\d+) use=(-?\d+) inst=(-?\d+)"
                      r"(?:.*? wel=(-?[\d.]+) inc=(-?[\d.]+))?", line)
        if not m:
            continue
        month, tag, bal, use, inst = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))
        gen = use + bal
        if tag not in best or gen > best[tag][0]:
            best[tag] = (gen, use, inst)
        if m.group(6) is not None and month != "January":
            money[tag].append((float(m.group(6)), float(m.group(7))))
    median = lambda xs: sorted(xs)[len(xs) // 2]
    welfare = {tag: (median([w for w, _ in v]), median([i for _, i in v])) for tag, v in money.items()}
    return best, welfare


def save_data(path):
    t = open(path, "rb").read().decode("utf-8", "replace")
    ci = t.find("\ncountry_manager={")
    se = t.find("\nstates={")
    ids = {m.group(1): m.group(2) for m in re.finditer(r'\n(\d+)=\{\n\t(?:is_main_tag=yes\n\t|civil_war=yes\n\t)*definition="?(\w+)"?\n', t[ci:se])}
    i = t.find("\ninstitutions={")
    j = re.compile(r"\n\}\n[a-z_]+=").search(t, i + 10).start()
    levels = collections.defaultdict(dict)
    # institutions the AI is resizing carry target= and growth= before country=
    for m in re.finditer(r"\n\d+=\{\n\tinstitution=(\w+)\n\tinvestment=(\d+)\n(?:\t\w+=[^\n]*\n)*?\tcountry=(\d+)\n", t[i:j]):
        levels[ids.get(m.group(3), "?")][m.group(1)] = int(m.group(2))
    # state id -> (region, owner tag); pops per state
    region = {}
    for m in re.finditer(r"\n(\d+)=\{\n\tcapital=\d+\n\n\tcountry=(\d+)\n(.*?)\n\tregion=\"?(STATE_\w+)\"?", t[se:se + 300000000], re.S):
        if len(m.group(3)) < 200000:
            region[m.group(1)] = (m.group(4), ids.get(m.group(2), "?"))
    pi = t.find("\npops={")
    pe = re.compile(r"\n\}\n[a-z_]+=").search(t, pi + 10).start()
    pop = collections.Counter()
    for m in re.finditer(r"\n\d+=\{\n(.*?)\n\}(?=\n\d+=|\n\t\})", t[pi:pe], re.S):
        b = m.group(1)
        loc = re.search(r"\n\tlocation=(\d+)", b)
        if loc and loc.group(1) in region:
            pop[region[loc.group(1)]] += sum(int(x) for x in re.findall(r"\n\t(?:workforce|dependents)=(\d+)", b))
    # staffed share and weekly cost per level (the government's share of their losses) of each country's administrations
    bi = t.find("\nbuilding_manager=")
    be = re.compile(r"\n\}\n[a-z_]+=").search(t, bi + 10).start()
    staff = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for m in re.finditer(r"\n\d+=\{\n\tbuilding=\"?building_government_administration\"?\n\tlevels?=(\d+)\n(.*?)\n\}(?=\s*\n\d+=|\s*\n\t\})", t[bi:be], re.S):
        s = re.search(r"\n\tstate=(\d+)", m.group(2))
        f = re.search(r"\n\tstaffing=([0-9.e]+)", m.group(2))
        g = re.search(r"\n\tgovernment_dividends=(-?[0-9.e]+)", m.group(2))
        if s and s.group(1) in region:
            st = staff[region[s.group(1)][1]]
            st[0] += int(m.group(1))
            st[1] += float(f.group(1)) if f else 0.0
            st[2] += -float(g.group(1)) if g else 0.0
    staffing = {tag: (v[1] / v[0] if v[0] else None) for tag, v in staff.items()}
    admin_cost = {tag: v[2] / v[0] for tag, v in staff.items() if v[0] and v[2] > 0}
    return levels, pop, staffing, admin_cost


def history_admins():
    """(state, tag) -> [path, start, end, levels] of the administration levels in the building history."""
    out = {}
    texts = {}
    d = os.path.join(WT, "common", "history", "buildings")
    for fn in sorted(os.listdir(d)):
        if fn == os.path.basename(NEW_ADMIN):
            continue
        path = os.path.join(d, fn)
        t = open(path, "rb").read().decode("utf-8-sig")
        texts[path] = t
        for sm in re.finditer(r"\n\ts:(STATE_\w+)=\{", t):
            send = t.find("\n\t}", sm.end())
            for rm in re.finditer(r"\n\t\tregion_state:(\w+)=\{", t[sm.end():send]):
                rs = sm.end() + rm.end()
                rend = t.find("\n\t\t}", rs)
                for cm in re.finditer(r'\n\t\t\tcreate_building=\{\r?\n\t\t\t\tbuilding="building_government_administration"', t[rs:rend]):
                    cs = rs + cm.end()
                    cend = t.find("\n\t\t\t}", cs)
                    lv = re.search(r"levels=(\d+)", t[cs:cend])
                    out[(sm.group(1), rm.group(1))] = [path, cs + lv.start(1), cs + lv.end(1), int(lv.group(1))]
    return out, texts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("save")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    best, welfare = probe_lines(a.log)
    levels, pop, staffing, admin_cost = save_data(a.save)
    admins, texts = history_admins()
    lines = ["# Generated by docs/maintenance/fit_starting_institutions.py: the 1946 institutions of the countries whose",
             "# budget or bureaucracy cannot run their law package's levels. Social security is lowered to the highest level",
             "# whose welfare payments stay within a tenth of the country's income (none where even level 1 pays more), and",
             "# every institution of a country whose bureaucracy usage exceeds its generation is scaled to what it can run",
             "# (each at least level 1). CWP 1.5 started almost every country without institutions; at the package levels",
             "# welfare took 23% of the world's government income and a third of the world wasted all of its taxes on",
             "# bureaucracy deficits in 1946.",
             "GLOBAL = {"]
    edits = collections.defaultdict(list)
    new_admin = collections.defaultdict(list)
    report = []
    for tag in sorted(set(best) | set(welfare)):
        lv = levels.get(tag, {})
        total = sum(lv.values())
        new = dict(lv)
        notes = []
        no_welfare = False
        if SOCIAL_SECURITY in lv and tag in welfare:
            w, income = welfare[tag]
            ss = lv[SOCIAL_SECURITY]
            if w > 0 and ss > 0:
                cap = min(ss, int(math.floor(WELFARE_SHARE * max(income, 0.0) / (w / ss) + 1e-9)))
                if cap < 1:
                    # 1.14 runs an institution at level 1 at least while its law stands: no welfare law, as in CWP 1.5
                    no_welfare = True
                    del new[SOCIAL_SECURITY]
                    notes.append("no social security (level 1 would pay %.0fk of %.0fk income in welfare)" % (w / ss / 1000, income / 1000))
                elif cap < ss:
                    new[SOCIAL_SECURITY] = cap
                    notes.append("social security %d -> %d (welfare %.0fk of %.0fk income)" % (ss, cap, w / 1000, income / 1000))
        gen, use, inst = best.get(tag, (0, 0, 0))
        trimmed = False
        hist = {st: admins[(st, tg)][3] for (st, tg) in admins if tg == tag}
        a_hist = sum(hist.values())
        cost = admin_cost.get(tag)
        income = welfare.get(tag, (0.0, 0.0))[1]
        if a_hist and cost and income > 0 and gen >= use and a_hist * cost > ADMIN_SHARE * income:
            per_adm = max(0.0, gen - GEN_BASE) / a_hist
            need = {st: min(n, max(1, int(math.ceil(max(0.0, pop.get((st, tag), 0) / 10000.0 - STATE_TAX_CAPACITY)
                                                     / CAPACITY_PER_LEVEL)))) for st, n in hist.items()}
            inst_min = inst / total * len(new) if total else 0.0
            a_bur = int(math.ceil(max(0.0, (use - inst + inst_min) * SPARE - GEN_BASE) / per_adm)) if per_adm else a_hist
            a_aff = int(math.floor(ADMIN_SHARE * income / cost))
            target = min(a_hist, max(a_aff, sum(need.values()), a_bur))
            if target < a_hist:
                cut = a_hist - target
                excess = {st: hist[st] - need[st] for st in hist}
                shares = {st: cut * e / sum(excess.values()) for st, e in excess.items()}
                dec = {st: int(math.floor(s + 1e-9)) for st, s in shares.items()}
                for st, s in sorted(shares.items(), key=lambda x: x[1] - math.floor(x[1] + 1e-9), reverse=True)[:cut - sum(dec.values())]:
                    dec[st] += 1
                for st, d in dec.items():
                    if d:
                        edits[admins[(st, tag)][0]].append((admins[(st, tag)], -d))
                notes.append("administrations %d -> %d (cost %.0fk of %.0fk income; tax capacity needs %d, institutions at "
                             "level 1 need %d)" % (a_hist, target, a_hist * cost / 1000, income / 1000, sum(need.values()), a_bur))
                gen = GEN_BASE + target * per_adm
                trimmed = True
        if inst > 0 and total:
            per_level = inst / total
            base = use - inst
            inst1 = per_level * sum(new.values())
            if (base + inst1) * SPARE > gen:
                f = max(0.0, min(1.0, (gen / SPARE - base) / inst1))
                new = {k: max(1, int(math.floor(v * f + 1e-9))) for k, v in new.items()}
                inst2 = per_level * sum(new.values())
                short = (base + inst2) * SPARE - gen
                add = int(math.ceil(short / ADMIN_PER_LEVEL)) if short > 0 and not trimmed else 0
                staffed = staffing.get(tag)
                note = "bureaucracy gen %d use %d -> %d, institution levels %d -> %d" % (
                    gen, use, round(base + inst2), total, sum(new.values()))
                if add and staffed is not None and staffed < MIN_STAFFING:
                    note += ", short %d with administrations %d%% staffed: none added" % (round(short), round(100 * staffed))
                    add = 0
                elif add:
                    note += ", +%d administration" % add
                notes.append(note)
                if add:
                    states = sorted(((p, st) for (st, tg), p in pop.items() if tg == tag and p > 0), reverse=True)
                    tot = sum(p for p, _ in states) or 1
                    shares = [(st, add * p / tot) for p, st in states]
                    alloc = {st: int(math.floor(s)) for st, s in shares}
                    for st, s in sorted(shares, key=lambda x: x[1] - math.floor(x[1]), reverse=True)[:add - sum(alloc.values())]:
                        alloc[st] += 1
                    for st, n in alloc.items():
                        if not n:
                            continue
                        if (st, tag) in admins:
                            edits[admins[(st, tag)][0]].append((admins[(st, tag)], n))
                        else:
                            new_admin[st].append((tag, n))
        changed = {k: v for k, v in new.items() if v != lv[k]}
        if notes:
            report.append("%-4s %s" % (tag, "; ".join(notes)))
        if changed or no_welfare:
            lines.append("\tc:%s ?= {" % tag)
            if no_welfare:
                lines.append("\t\tactivate_law = law_type:law_no_social_security")
            for k in sorted(changed):
                lines.append("\t\tset_institution_investment_level = { institution = %s level = %d }" % (k, changed[k]))
            lines.append("\t}")
    lines.append("}")
    print("\n".join(report))
    print("countries refitted:", len(report))
    if not a.write:
        return
    with open(os.path.join(WT, OUT), "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote", OUT)
    for path, items in edits.items():
        t = texts[path]
        for (p, s, e, old), n in sorted(items, key=lambda x: -x[0][1]):
            t = t[:s] + str(old + n) + t[e:]
        crlf = b"\r\n" in open(path, "rb").read(4096)
        with open(path, "w", encoding="utf-8-sig", newline="\r\n" if crlf else "\n") as fh:
            fh.write(t.replace("\r\n", "\n"))
        print("changed administrations in", os.path.relpath(path, WT), len(items))
    if new_admin:
        out = ["# Generated by docs/maintenance/fit_starting_institutions.py: administrations for states of countries whose",
               "# bureaucracy could not run even the lowest level of their institutions in 1946.", "BUILDINGS={"]
        for st in sorted(new_admin):
            out.append("\ts:%s={" % st)
            for tag, n in new_admin[st]:
                out += ["\t\tregion_state:%s={" % tag, "\t\t\tcreate_building={", '\t\t\t\tbuilding="building_government_administration"',
                        "\t\t\t\tadd_ownership={", "\t\t\t\t\tcountry={", '\t\t\t\t\t\tcountry="c:%s"' % tag, "\t\t\t\t\t\tlevels=%d" % n,
                        "\t\t\t\t\t}", "\t\t\t\t}", "\t\t\t\treserves=1",
                        '\t\t\t\tactivate_production_methods={ "pm_no_administration_outsourcing" "pm_mail_couriers" "pm_filing_systems" }',
                        "\t\t\t}", "\t\t}"]
            out.append("\t}")
        out.append("}")
        with open(os.path.join(WT, NEW_ADMIN), "w", encoding="utf-8-sig", newline="\r\n") as fh:
            fh.write("\n".join(out) + "\n")
        print("wrote", NEW_ADMIN, len(new_admin), "states")


if __name__ == "__main__":
    main()
