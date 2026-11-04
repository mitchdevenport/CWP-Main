"""Regenerate CWP's terminology overrides from the installed game's English and Japanese localization.

CWP 1.5 calls battalions divisions and literacy the Education Index throughout the interface. The overrides in
localization/<language>/replace/cwp_terminology_l_<language>.yml copy the base game's current text for every
interface, concept, modifier and trigger key that mentions battalions or literacy and substitute only the displayed
words (data functions, $references$, @icons! and #formatting stay as they are), so they keep the base game's wording,
data functions and icons. Event, journal entry, tutorial and DLC story text is left alone, as in CWP 1.5, and keys
the mod defines elsewhere are skipped.

usage: python docs/maintenance/cwp_terminology.py [--game <Victoria 3 install folder>]   (run from the mod root)
"""
import argparse
import glob
import os
import re

DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3"
KEY = re.compile(r'^\s+([A-Za-z0-9_.\-]+):(\d*)\s*"(.*)"\s*$', re.M)
PROTECT = re.compile(r"(\[[^\]]*\]|\$[^$\s]*\$|@\w+!|#\w+|#!|\\n)")
SKIP_FILES = ("ip3_serbia", "tutorial")
SKIP_KEYS = ("je_", "ACHIEVEMENT_", "lesson_", "serbian_")
TERMS = re.compile(r"\bbattalions?\b|\bliteracy\b|\bliterate\b", re.I)

EN = [(r"\bBattalions\b", "Divisions"), (r"\bbattalions\b", "divisions"), (r"\bBattalion\b", "Division"),
      (r"\bbattalion\b", "division"), (r"\bLiteracy [Rr]ate\b", "Education Index"),
      (r"\bliteracy rate\b", "education index"), (r"\bLiteracy\b", "Education Index"),
      (r"\bliteracy\b", "education index"), (r"\bIlliterate\b", "Uneducated"), (r"\billiterate\b", "uneducated"),
      (r"\bLiterate\b", "Educated"), (r"\bliterate\b", "educated"),
      (r"\b([Aa]) ([Ee]ducation [Ii]ndex|[Ee]ducated)", lambda m: m.group(1) + "n " + m.group(2))]
JA = [("大隊", "師団"), ("識字率", "教育指数"), ("読み書きできます", "高度な教育を受けています"),
      ("読み書きができる", "高度な教育を受けた")]
FIXED = {"english": {"concept_literate": "Educated"}, "japanese": {"concept_literate": "教育的"}}  # CWP 1.5's
FIRST_SENTENCE = {  # CWP 1.5's definition of the Education Index
    "english": ("The percentage or absolute number of individuals in a [concept_pop] who can read and write.",
                "An index of the overall level of education of [concept_pop]."),
    "japanese": ("[concept_pop]に含まれる個人のうち、読み書きができる人の割合または絶対数です。",
                 "[concept_pop]の全体的な教育水準の指数です。"),
}
EXTRA = ("concept_literacy_desc",)  # names the concept only through $concept_literacy$, but carries the definition


def load(pattern, skip_own=False):
    out = {}
    for path in glob.glob(pattern, recursive=True):
        base = os.path.basename(path)
        if any(s in base for s in SKIP_FILES) or (skip_own and base.startswith("cwp_terminology_l_")):
            continue
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for key, version, text in KEY.findall(f.read()):
                out[key] = (version, text)
    return out


def substitute(text, rules, regex):
    parts = PROTECT.split(text)
    for i in range(0, len(parts), 2):
        for old, new in rules:
            parts[i] = re.sub(old, new, parts[i]) if regex else parts[i].replace(old, new)
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--game", default=DEFAULT_GAME, help="Victoria 3 install folder (containing game/)")
    args = parser.parse_args()
    vanilla = os.path.join(args.game, "game", "localization")
    base = {lang: load(os.path.join(vanilla, lang, "**", "*.yml")) for lang in ("english", "japanese")}
    mod = {lang: load(os.path.join("localization", lang, "**", "*.yml"), skip_own=True) for lang in base}
    keys = sorted(k for k, (_, text) in base["english"].items()
                  if "." not in k and not k.startswith(SKIP_KEYS)
                  and (k in EXTRA or TERMS.search("".join(PROTECT.split(text)[0::2]))))
    skipped = [k for k in keys if k in mod["english"] or k in mod["japanese"]]
    if skipped:
        print("skipped, defined by the mod:", " ".join(skipped))
    for lang, rules, regex in (("english", EN, True), ("japanese", JA, False)):
        lines = [f"l_{lang}:"]
        for k in keys:
            if k in skipped or k not in base[lang]:
                continue
            version, text = base[lang][k]
            new = FIXED[lang].get(k) or substitute(text.replace(*FIRST_SENTENCE[lang]), rules, regex)
            if new != text:
                lines.append(f' {k}:{version} "{new}"')
        path = os.path.join("localization", lang, "replace", f"cwp_terminology_l_{lang}.yml")
        with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        print(path, len(lines) - 1, "keys")


if __name__ == "__main__":
    main()
