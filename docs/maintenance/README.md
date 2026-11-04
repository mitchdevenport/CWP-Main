# Maintenance tools

Scripts and checks for keeping the mod working across Victoria 3 updates. Run them from the mod root.

## After every game update

1. `python docs/maintenance/vanilla_placeholders.py` - Victoria 3 1.14 does not honour
   `replace_paths` in `.metadata/metadata.json` reliably, so every vanilla file inside a folder the mod
   replaces is overridden by a blank "CWP placeholder" file with the same name. The script adds
   placeholders for new vanilla files and reports placeholders whose vanilla file is gone (`--prune`
   removes them). Never delete a placeholder by hand; when the mod needs a vanilla file's content, put
   CWP's version at that path instead (see `common/customizable_localization/cwp_vanilla_custom_loc.txt`
   for vanilla definitions that CWP text still uses). Files that match a vanilla file name except for letter
   case are renamed to the vanilla spelling: the game would otherwise load both spellings, so on Windows the
   mod file ran twice (country histories were applied twice). Stage the renames with `git add -A`.
2. `python docs/maintenance/naval_network.py` - rebuilds `common/travel_network/naval_network.txt`
   (the fleet waypoint graph) for the CWP map from vanilla's graph. Re-run it when the map or vanilla's
   network changes. Requires numpy and Pillow.
3. `python docs/maintenance/restore_flavour_events.py` - rebuilds CWP's copies of the base game's flavour
   events (law debates, election campaigns, revolutions, exiles, decrees, natural disasters, ...) from the
   installed game: the event files CWP 1.5 had, limited to the events it used and adapted to CWP's buildings,
   laws and 1946 technology level, plus the base game modifiers, triggers and hooks they need
   (`cwp_vanilla_event_*.txt`, `common/on_actions/cwp_flavour_events_on_actions.txt`). Review the diff; when
   the base game renames something the events use, extend the script's mappings rather than editing the output.
4. Start the game with the mod and check `error.log` in the Victoria 3 user folder after reaching the
   main menu and after starting a game.

Known load-time messages that are not caused by script errors: six "Naval node from spline anchor ..."
messages (anchors in CWP's spline network that only the map editor can fix), the terrain manipulator
checksum warning (fixed by saving in the map editor), and the `CInterestGroupTypeDatabase::ExpectedNumItems`
assertion (CWP has more interest groups than vanilla). "submarine_base_entity has no attach point named
loc_figurehead" appears when a submarine leads a fleet; the base game's submarine has no such locator either. During a campaign the engine may also log single
assertions about shipping lanes from a `NULL_OBJ` state (probably the ports behind those spline anchors), dead
or invalid formations travelling, `War.GetWarParticipant` and interest group leaders that cannot be generated.
None of them names a CWP script location and the war support values involved are vanilla's, so they look
engine-side, but that has not been proven.

An `Assertion failed: NGameState::GameStateAccess ...` line after unpausing means gamestate script (events,
on_actions, effects) read hidden AI or interface-only state, which desyncs multiplayer games. Find the
cause by disabling on_action hooks until it disappears. `has_healthy_economy` is such a trigger: use
`cwp_has_healthy_economy` (common/scripted_triggers/cwp_fiscal_triggers.txt) instead.

Journal entries added with `add_journal_entry` must not use `can_deactivate = yes` unless they also have
`is_shown_when_inactive`: once deactivated they never reactivate, and the leftover inactive entry makes later
`add_journal_entry` calls fail ("... already has a journal entry of type ..."). End them with `invalid` instead.

Company types need no extra buildings, but `common/scripted_effects/cwp_company_effects.txt` lists every company
type to clean up the company buildings left behind when a civil war or secession ends; add new company types there.

Politics rules the 1.14 engine enforces:
- A distribution-of-power law only holds elections (and gets parties) if the law's own `modifier` grants voting
  power; voting power from the voting institution's `institution_modifier` does not count. The franchise laws
  therefore carry a token 1 point of voting power and the institution supplies the rest.
- Scripted rulers (`ruler = yes` in `common/history/characters`) must fit the transfer of power: under
  dictatorial or hereditary rule they may not lead their interest group, under presidential rule they must,
  and under parliamentary rule they must lead the strongest interest group in the government. Violations are
  logged at startup as "The ruler of X is scripted to be ...".
- Once parties exist the engine forms its own government, so governments of countries that hold elections at
  the start are set in `common/history/governments/cwp_starting_governments.txt`, not with
  `add_ruling_interest_group` in country history.
- `gov_parliamentary_monarchy` (prime minister governs, monarchy names and flags) applies to monarchies with the
  `cwp_parliamentary_monarchy` variable; set it before enacting the monarchy law.
- A country takes the first government type (in file load order) whose `possible` trigger passes.
  `law_colonial_administration` is a variant of `law_monarchy`, so the colonial and military administrations in
  `common/government_types/cwp_colonial_administrations.txt` must load before the monarchies in `cwp_monarchy.txt`.
- Every country that owns land at the start needs a file in `common/history/countries` with its law package and
  technologies. Without one it starts as an absolute monarchy with the default laws and no technologies.
- Electoral confidence starts at the freedom index (urbanization and literacy, `eagle_burger_freedom_index`), which
  is low for most of the 1946 world, and CWP has no events that raise it. Countries that hold elections at the start
  therefore get the base game's decaying grace for newly introduced elections (`initialize_electoral_confidence`).
- A government's share of the votes, worth up to 65 legitimacy, belongs to the parties in it: interest groups that
  govern without their party bring none, and a party can start with none until its first election (Britain's
  Labour did, while the American Democrats start with 24%). Britain therefore holds its first election in February
  1946, as in CWP 1.5 (and as the base game does in 1836).
- At the start the game removes the interest groups that cost legitimacy from each government
  (`STARTUP_MIN_LEGITIMACY_IG_BARRIER`), whether they were set in country history or in `common/history/governments`.
  Check a starting government in game (the Government tab, or `is_in_government` on day one). CWP 1.5's Soviet
  government (the Trade Unions and Armed Forces) cost the USSR all its legitimacy and was reduced to Stalin's
  Intelligentsia, so the USSR starts with the Intelligentsia and the Bureaucrats (Stalin's group in CWP 1.5).
- High and very high taxes cost 5 and 10 legitimacy as in CWP 1.5 (the base game's 10 and 20,
  `common/static_modifiers/00_code_static_modifiers.txt`): 23 countries start with the high or very high taxes of
  their CWP 1.5 history.

Economy rules:
- The building history (`common/history/buildings`) is generated. The generator left Czechoslovakia, Yugoslavia,
  Romania, Bulgaria, Albania, North Korea and French West Africa with nothing but government buildings, so those
  countries had almost no GDP or income and fell into default within weeks. After regenerating the
  history, run `python docs/maintenance/restore_starting_economies.py`: it rebuilds the economy of every state whose
  owner has no economic building from CWP 1.5's building history (see the script for the conversion rules).
- Starting government administrations use filing systems and are sized to the bureaucracy each country used on
  1 February 1946 (about 25% spare), without leaving any state short of tax capacity. Administrations several
  times larger than needed cost more than the country earns and push it into default within months.
- Starting universities cost at most a tenth of their country's income on 1 February 1946 (the great powers spend
  1-5%). The generator had given small countries dozens of levels (Uruguay 117, Ecuador 69) that cost several times
  their income.
- Inflation (`inflation_growth` in `common/script_values/fiscal_values.txt`) accumulates the price levels of a
  basket of consumer goods every month and never reverts on its own, so a good that is persistently cheap or
  expensive in every market drives every country into deflation or inflation. Check the basket's prices in a long
  campaign before adding goods to it.
- A money supply 10% or more below its target subtracts from inflation every month, so a country must answer a
  shrinking money supply with an expansionary policy or fall into a deflation spiral (below -10% the deflation
  modifier cuts production). The AI sets the monetary policy of every country it runs; the Dynamic Control game
  rule leaves it to the player only for players' countries (`onaction_ai_monetary_policy_calculation`).
- Investment pools are soft-capped at the gold reserves limit (`onaction_investment_pool_softcap`): above it the
  `full_investment_pool` modifier lowers the contribution of every pop type that pays into the pool. Keep its list in
  step with the contributions in the base values of `common/static_modifiers/00_code_static_modifiers.txt`.

Power bloc rules:
- The Western and Eastern Blocs stand in for CWP 1.5's diplomatic alignment with a superpower. Members run by the AI
  only leave (or switch blocs through invitations, join requests or treaties) when the superpower falls below great
  power rank, relations with it turn hostile, or their own politics turn against it (`can_leave` in
  `common/power_bloc_identities/cwp_power_bloc_identities_ideological_union.txt`).
- The AI expels members when its bloc's cohesion is low, and cohesion follows the leader's legitimacy, which is low in
  the first weeks of 1946. Every bloc therefore starts the game at least half cohesive with the one-year
  `cwp_postwar_alignment` modifier (`on_game_started` in `common/on_actions/00_code_on_actions.txt`).

Military rules:
- Starting armies and fleets come from `common/history/military_formations`. The engine adds formation units on
  top of the barracks in `common/history/buildings` (those form an extra default army), so a country with
  starting formations has no barracks in the building history; set its barracks training with
  `activate_production_method` in its formation block instead.
- Fleets are made of individual ships (`ship = { type = ship_type:... count = N }`). Naval administrations only
  recruit their crews (1,000 sailors per level), so the building history must give enough levels for them.
- Nuclear warheads are the `nuclear_stockpile` variable (`common/script_values/wmd_values.txt`). Storage is two per
  weapons facility level plus the silos' capacity; warheads beyond it decay at the stockpile divided by the storage
  each month. A country that completes the atomic bomb journal entry gets one warhead and no facility, so with no
  storage the overflow decay is skipped (CWP 1.5 divided by zero there; with the divisor clamped to 1 the warhead
  was destroyed at the first monthly tick). The AI does not build facilities or silos on its own.
- Do not roll random outcomes while the AI presses a scripted button, or in a journal entry's pulse. A `random_list`
  in a button's effect, or in an event the button fires (even a day later), came out the same at every AI press in a
  campaign: 25 plain failures in a row for the Soviet atomic tests in one run (rolls in scripted GUIs clicked by a
  player vary). Rolled in the program journal entry's weekly pulse, a reloaded campaign's tests still repeated (15
  failures in 15). `conduct_nuclear_test_button` only sets `nuclear_test_pending`, and the global monthly pulse rolls
  the test (`cwp_military_monthly_pulse` in `common/on_actions/cwp_military_on_actions.txt`).

The AI may downsize any government building it considers unprofitable; buildings it must keep (the WMD
infrastructure, conscription centers) are `downsizeable = no`.

## End-to-end tests

`tools/scripted_tests/cwp_systems.txt` checks that the mod's systems work in a real campaign: the Cold
War blocs, UN, IMF, currencies and starting companies exist at the start; the economy and climate are
simulated monthly; and the AI forms NATO and the Warsaw Pact, tests Soviet atomic bombs, holds UN votes
(without any vote entry getting stuck), partitions India, forms West Germany, frees Libya, settles the
Newfoundland question, decolonizes and stages coups before 1961.

1. Start a 1946 game (observing is fine) and open the console.
2. Run `scripted_tests none` (without `none` the game saves after every failed test).
3. Run the game at full speed until 1961.
4. Read `tests.txt` in the Victoria 3 user folder (`Documents/Paradox Interactive/Victoria 3`).

The milestones depend on AI decisions, so an occasional failure of a historical milestone is not
necessarily a bug; a failure of the start-of-game checks is.
