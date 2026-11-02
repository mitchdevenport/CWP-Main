# Maintenance tools

Scripts and checks for keeping the mod working across Victoria 3 updates. Run them from the mod root.

## After every game update

1. `python docs/maintenance/vanilla_placeholders.py` - Victoria 3 1.14 does not honour
   `replace_paths` in `.metadata/metadata.json` reliably, so every vanilla file inside a folder the mod
   replaces is overridden by a blank "CWP placeholder" file with the same name. The script adds
   placeholders for new vanilla files and reports placeholders whose vanilla file is gone (`--prune`
   removes them). Never delete a placeholder by hand; when the mod needs a vanilla file's content, put
   CWP's version at that path instead (see `common/customizable_localization/cwp_vanilla_custom_loc.txt`
   for vanilla definitions that CWP text still uses).
2. `python docs/maintenance/naval_network.py` - rebuilds `common/travel_network/naval_network.txt`
   (the fleet waypoint graph) for the CWP map from vanilla's graph. Re-run it when the map or vanilla's
   network changes. Requires numpy and Pillow.
3. Start the game with the mod and check `error.log` in the Victoria 3 user folder after reaching the
   main menu and after starting a game.

Known load-time messages that are not caused by script errors: six "Naval node from spline anchor ..."
messages (anchors in CWP's spline network that only the map editor can fix), the terrain manipulator
checksum warning (fixed by saving in the map editor), and the `CInterestGroupTypeDatabase::ExpectedNumItems`
assertion (CWP has more interest groups than vanilla). During a campaign the engine may also log single
assertions about shipping lanes from a `NULL_OBJ` state (probably the ports behind those spline anchors), dead
or invalid formations travelling, `War.GetWarParticipant` and interest group leaders that cannot be generated;
none of them comes from CWP script (the war support values are vanilla's).

An `Assertion failed: NGameState::GameStateAccess ...` line after unpausing means gamestate script (events,
on_actions, effects) read hidden AI or interface-only state, which desyncs multiplayer games. Find the
cause by disabling on_action hooks until it disappears. `has_healthy_economy` is such a trigger: use
`cwp_has_healthy_economy` (common/scripted_triggers/cwp_fiscal_triggers.txt) instead.

Journal entries added with `add_journal_entry` must not use `can_deactivate = yes` unless they also have
`is_shown_when_inactive`: once deactivated they never reactivate, and the leftover inactive entry makes later
`add_journal_entry` calls fail ("... already has a journal entry of type ..."). End them with `invalid` instead.

Company types need no extra buildings, but `common/scripted_effects/cwp_company_effects.txt` lists every company
type to clean up the company buildings left behind when a civil war or secession ends; add new company types there.

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
