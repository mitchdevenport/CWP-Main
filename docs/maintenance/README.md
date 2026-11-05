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
4. `python docs/maintenance/cwp_terminology.py` - regenerates CWP 1.5's terminology (divisions for battalions,
   the Education Index for literacy) in `localization/<language>/replace/cwp_terminology_l_<language>.yml` from the
   base game's current English and Japanese text, substituting only the displayed words, so the overrides keep the
   base game's latest wording, data functions and icons. Text that needs more than the substitution belongs in the
   mod's own localization files: the script skips keys the mod defines elsewhere.
5. Start the game with the mod and check `error.log` in the Victoria 3 user folder after reaching the
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
  power. The engine also ignores the voting power, the voting wealth cutoff and the legitimacy from votes that come
  from institutions, so the voting institution (Electoral Administration) could not widen the franchise level by
  level as designed: with only a token point of voting power, census suffrage gave most pops no votes at all and
  40 of the 54 countries with elections in 1946 held them without a single voter. The franchise laws therefore carry
  what the institution gives at its full investment (census suffrage: wealth cutoff 10, 45 voting power from
  literate pops, 85 legitimacy from votes; universal suffrage: no cutoff, 50 voting power, 110), which are the base
  game's values; the institution itself only adds authority. Check a franchise in game with the Political
  Strength tooltip of a pop, which lists the voting cutoff and the number of votes.
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
- A government's share of the votes, worth up to 85 legitimacy under census suffrage, belongs to the parties in it:
  interest groups that govern without their party bring none. The votes of the start come from an election the game
  holds on 1 January 1946 (Britain's Labour government starts with about a third of them); Britain then holds its first real
  election in February 1946, as in CWP 1.5 (and as the base game does in 1836).
- At the start the game removes the interest groups that cost legitimacy from each government
  (`STARTUP_MIN_LEGITIMACY_IG_BARRIER`), whether they were set in country history or in `common/history/governments`.
  Check a starting government in game (the Government tab, or `is_in_government` on day one). CWP 1.5's Soviet
  government (the Trade Unions and Armed Forces) cost the USSR all its legitimacy and was reduced to Stalin's
  Intelligentsia, so the USSR starts with the Intelligentsia and the Bureaucrats (Stalin's group in CWP 1.5).
- High and very high taxes cost 5 and 10 legitimacy as in CWP 1.5 (the base game's 10 and 20,
  `common/static_modifiers/00_code_static_modifiers.txt`): 23 countries start with the high or very high taxes of
  their CWP 1.5 history.
- Communist and Nationalist China and Indonesia start with CWP 1.5's `effect_last_stand` (five years in which
  casualties and lost battles cost no war support). Without it the Communists capitulated within two years in every
  1946-1955 test. With it the civil war is a toss-up decided by exhaustion and occupation: of two 1946-1950 tests
  one went to the People's Republic (31 states by 1950, the Nationalists in Formosa after their Great Retreat) and
  one to the Nationalists, where CWP 1.5's own run went to the People's Republic. 1.14's Nationalists are richer
  (the 1946 package's land-based taxation on 400 million peasants) and fund mechanized brigades on 1.14's large
  credit, but CWP 1.5's consumption-based (Nationalist) and per-capita (Communist) taxation did not help the
  Communists: the Nationalists won both tests with it. CWP 1.5's starting corruption effects (`effect_corruption_*`)
  fired events it did not have, so they are not restored.

Law rules:
- A law with a `parent` is a variant: in 1.14 it inherits its parent's ideological stances and cannot be rated itself,
  so ideologies rate only parent laws (`docs/ideologies/validate.py` skips variants).
- The game gives a new country the first law of each group it can have, and it also applies `can_enact` to the law a
  country holds ("not permitted to retain law ..."). `unlocking_laws` naming laws of the same group (CWP 1.5's
  one-step ladders) therefore left countries created during the game without any law in the group ("has no active law
  for some reason" in error.log). These ladders are `can_enact` conditions that also accept the law itself and a
  country with no law in the group yet (`cwp_has_no_<group>_law`), and each group's default law comes first in its file.
- The law groups the 2025 rebuild dropped from CWP 1.5 (centralization, nationalization, environmental regulations,
  family planning, biotech and recreational drugs) are restored in `common/laws/cwp_04/11/16/23/26/27_*.txt`. Their
  interest group stances sit on the base-game-derived ideologies, following the developers' mapping of CWP 1.5's
  interest groups onto the current ones; the ideology pack's own ideologies are capped at four (characters) and three
  (interest groups) law groups and stay as designed. The game gives every new country the first law of each group
  before history runs (CWP 1.5 relied on this, which left 19 countries under total prohibition), so
  `common/history/global/cwp_restored_laws_global.txt` first gives every country CWP 1.5's most common law in each
  group (`effect_cwp_restored_law_start_defaults`) and then the laws of CWP 1.5's country histories. Countries created
  later inherit their origin's laws; decolonized ones start confederated, as in CWP 1.5. Effects run on enactment
  wait for the 1946 setup (`cwp_restored_laws_setup`): the first drug law, total prohibition, banned tobacco, liquor and
  wine in every country when the game assigned it.
- CWP 1.5 enforced nationalization through ownership production methods, one more sector per step. 1.14 has building
  ownership instead, so the laws work through its nationalization and privatization modifiers and the AI's
  `nationalization_desire` (`common/ai_strategies/00_default_strategy.txt`), whose middle steps add to each building's
  own `ai_nationalization_desire` (military industries and railways are nationalized, the rest kept).
- Environmental regulations set the lowest green technology (`pmg_green_tech_industry`) a polluting industry may
  use, as in CWP 1.5. Give the group to every new industry whose production methods generate pollution.

Party rules:
- The parties are CWP 1.5's seventeen (`common/parties/cwp_*_party.txt`, restored from CWP 1.5's; design notes in CWP
  1.5's `common/parties/_designDoc.md`); the base game's party files are placeholders. An interest group's join weight
  (its affiliation in 1.14) is CWP 1.5's: -5; +6 for the party's headliner (CWP 1.5's groups mapped onto the current
  ones as in the developers' interest group mapping; a fascist, feminist, green or pacifist leader for those parties,
  the ideology pack's second-wave feminists and greens included; Intelligentsia for the social democrats, democratic
  socialists and socialists only with CWP 1.5's stances on the executive system and nationalization); the party's
  morale (-10 to 10: +1 a year and at each government reshuffle for every governing member, -1 for every member out of
  government); its cohesion (about 7 a member: CWP 1.5 meant to count members sharing their mood, but its check
  counted every member, and its balance rests on that); a tenth of the summed popularity of its members' leaders; its
  clout (+5 for every powerful member, -1 for every other); all scaled by the number of groups joining before it (none
  from the sixth). The green party also grows with the world's temperature. The ideology pack's party families add +3
  when the group's leader belongs to the family (communists; social democrats and democratic socialists; liberals and
  libertarians).
- Victoria 3 1.5 formed parties as election campaigns began and read these weights once; 1.14 re-weighs affiliation
  all the time, so a party's standing would snowball as each group joined. The standing (cohesion, popularity, clout)
  is therefore stored half-yearly and when a campaign begins (`onaction_calc_party_cohesion` in
  `common/scripted_effects/cwp_party_effects.txt`), and between campaigns a member keeps its party (+100). Every
  country gets the variables in 1946 (`setup_parties`), released and decolonized countries when they appear.
- Which groups may join follows CWP 1.5's law stances, mapped to the current laws (representative democracy: census
  suffrage; consensus and direct democracy: universal suffrage; anocracy: single-party state; free market:
  laissez-faire; socialization: command economy or cooperative ownership; hereditary: monarchy; ...). A group passes a
  condition unless it opposes the law, but the ideology pack gives groups opinions on few laws: where a group has none
  and its CWP 1.5 counterpart started out failing the condition (Laborists the libertarians' consumption taxes,
  Moralists and Securocrats their decentralized police, ...), only the group's own support passes it. These come from
  CWP 1.5's starting ideologies (laws with a one-to-one counterpart; not the franchise laws); each such condition
  names the CWP 1.5 groups. The monarchist party needs a monarchy or `recently_abolished_monarchy` (ten years from the
  enactment of a republic). CWP 1.5's single-legal-party check (`only_valid_party`) is left out: nothing in CWP 1.5
  set it.
- The base game's free trade, military, radical, religious and revolutionary parties do not exist. Base game events
  and effects that name them use the party CWP 1.5 put in their place when it adapted those events (liberals for free
  trade, conservatives for the hawks, social democrats for the radicals, Christian democrats for the religious party):
  `restore_flavour_events.py` maps the restored events (`PARTIES`), and new references elsewhere must be mapped the
  same way. Party names for particular countries (CWP 1.5's for France, Bavaria, Germany and its zones and East
  Germany, then the developers') go in each party's `name` block before the generic name.
- With the developers' nine interest groups instead of CWP 1.5's eleven, democracies settle on two or three parties
  rather than CWP 1.5's three to six; groups that no party suits stay independent, as in CWP 1.5.

Economy rules:
- The building history (`common/history/buildings`) is generated. The generator left Czechoslovakia, Yugoslavia,
  Romania, Bulgaria, Albania, North Korea and French West Africa with nothing but government buildings, so those
  countries had almost no GDP or income and fell into default within weeks. After regenerating the
  history, run `python docs/maintenance/restore_starting_economies.py`: it rebuilds the economy of every state whose
  owner has no economic building from CWP 1.5's building history (see the script for the conversion rules).
- Starting government administrations use filing systems and are sized to the bureaucracy each country used on
  1 February 1946 (about 25% spare), without trimming any administration below what its own state's tax capacity
  needs. Administrations several times larger than needed cost more than the country earns and push it into
  default within months.
- The 1946 law packages (`common/scripted_effects/cwp_starting_law_packages.txt`) start most countries with a dozen
  institutions at levels 2-5, where CWP 1.5 started almost every country without any.
  `common/history/global/cwp_starting_institutions.txt` lowers them where the country's budget or bureaucracy
  cannot run them, and `common/history/buildings/cwp_starting_administrations.txt` and a few raised
  administrations give bureaucracy to countries that cannot run even level 1 of their institutions. Each level of
  social security tops every worker's wage up to another fifth of the normal wage: at the package levels welfare
  took 23% of the world's government income in February 1946 (CWP 1.5: about 1%; Britain paid a million a week,
  Yugoslavia and Bulgaria more than their whole income), so social security keeps the highest level whose payments
  stay within a tenth of income (the United States keep 4, Britain, France and the Soviet Union 1), and countries
  that cannot pay even level 1, the lowest an institution runs at while its law stands, start without social
  security, as almost every country did in CWP 1.5 (Italy, Japan, Poland, Spain and fifteen others). A bureaucracy
  deficit wastes taxes
  (all of them at twice the generation), and 42 countries started in one. Administrations costing more than 30% of
  their country's income while their bureaucracy is spare are trimmed to what that pays for, keeping every state's
  tax capacity and the institutions' needs at level 1 (Poland 212 levels to 46, Hungary 61 to 16, South Korea 228 to
  63; CWP 1.5 had 60, 7 and 30, and the AI cut them to about that by 1955 anyway, going bankrupt on the way).
  Generate all of it with `python docs/maintenance/fit_starting_institutions.py <debug.log> <save.v3> --write` from
  an observer run of the mod without the two files and with the building history as generated (the script describes
  the probe), and rerun it after changing the law packages, the building history or the institutions.
- Starting universities cost at most a tenth of their country's income on 1 February 1946 (the great powers spend
  1-5%). The generator had given small countries dozens of levels (Uruguay 117, Ecuador 69) that cost several times
  their income.
- CWP has its own pop types (`common/pop_types`); keep their flags in step with vanilla's. Without the 1.14
  `pays_land_tax` on peasants and farmers, land tax (all of Land-Based Taxation's tax on pops and part of the other
  taxation laws) collected nothing, and agrarian countries such as Communist China had almost no tax income.
- The base game's pop types stand in for CWP 1.5's and carry CWP 1.5's names where one is the other
  (`localization/<language>/replace/cwp_pop_types_l_<language>.yml`): clerks are Service Workers, bureaucrats
  Administrators, machinists Technicians, peasants Informal Workers, clergymen Clergy, soldiers Service Members,
  capitalists Investors and aristocrats Landlords. CWP 1.5 drew those pop types with the same base game icons
  (`gfx/interface/icons/pops_icons` holds its copies under its own names); shopkeepers and slaves had no CWP 1.5
  counterpart, and CWP 1.5's creatives, professionals and slum dwellers have no pop type of their own.
- The 1.5 release ran the AI's budget and production construction through ARoAI (it switched off the game's own
  government money spending and production building AI), which the port does not have. Its MONEY_SPENDING_* and
  PRODUCTION_BUILDING_* defines therefore never applied and are left at vanilla's (`common/defines/cwp_ai.txt`),
  except that construction is no longer a must-have once the investment pool holds 52 weeks of investment
  (`MONEY_SPENDING_CONSTRUCTION_MAX_INVESTMENT_POOL_WEEKS`): must-haves skip every budget check, and in 1947 the AI
  had queued 2,315 construction sectors while Bahrain, Iceland, Yemen and Saudi Arabia spent five to seventeen times
  their income building them. ARoAI only built what the budget allowed.
  Government administrations give tax capacity in 1.14 (one point per 10,000 taxed pops) on top of every state's
  own 100 (`state_tax_capacity_add` in the base values: CWP 1.5's and the base game's value), and taxation in a
  state is cut by the share of its pops above its capacity. The game's AI sizes administrations by bureaucracy alone
  (ARoAI spent a fifth of income on them and weighed the taxes lost), so it lets them shrink and the most populous
  states (China, India, the larger American states) collect a fraction of their taxes. With no capacity of their own
  (the dev branch had 0) states without an administration taxed nothing: in a 1946-1955 test, restoring it cut the
  world's untaxed share from 51% to 43%, raised tax revenue 18% and halved the countries in default (9 to 4).
  Scripting ARoAI's placement back in for the AI (new levels every month in the states losing the most taxes) did not
  help: in a 1946-1960 test India ended up with a third to twice as many administration levels but a quarter to a
  third less tax capacity and collected 19-36% less tax, while the world's untaxed share moved within the runs' own
  spread.
- Inflation (`inflation_growth` in `common/script_values/fiscal_values.txt`) accumulates the price levels of a
  basket of consumer goods every month and never reverts on its own, so a good that is persistently cheap or
  expensive in every market drives every country into deflation or inflation. Check the basket's prices in a long
  campaign before adding goods to it.
- A money supply 10% or more below its target subtracts from inflation every month, so a country must answer a
  shrinking money supply with an expansionary policy or fall into a deflation spiral (below -10% the deflation
  modifier cuts production). The AI sets the monetary policy of every country it runs; the Dynamic Control game
  rule leaves it to the player only for players' countries (`onaction_ai_monetary_policy_calculation`).
- The money supply's limits are the gold reserves limit plus the credit a country can draw on (`money_supply_max`).
  The 1.14 game can report negative credit, so use `cwp_credit_capacity` (credit, at least 0) wherever credit stands
  for capacity: with the raw value the limits turned negative and every money supply percentage changed sign. The
  monthly update always applies the policy's change and then clamps the money supply to its limits.
- Under the gold standard the interest rate is fixed and inflation moves a tenth as fast, so the money supply is
  the AI's only tool against inflation there. The AI's preference for loose money when it is in debt or its
  economy is unhealthy therefore yields to inflation of 10% or more (`common/script_values/fiscal_ai_values.txt`).
- Bretton Woods (`je_bretton_woods_agreement`) fails for every signatory once US inflation leaves -0.5 to 5%, while
  CWP 1.5 meant it to last until the United States ends it by decision (the AI after 1970). Under the gold standard
  the money supply moves inflation only once it is 10% off target, a year or more after a policy change, and the
  AI's gold reserve bonuses kept a gold-rich United States contracting until inflation fell below zero: test games
  lost the agreement in the 1950s both below -0.5 and above 5%. While it holds, the AI's United States therefore
  steers inflation toward 2.5% by its trend (`cwp_bw_inflation_growth_excess`); a rule on the level of inflation
  alone overshot both ways.
- A pegged currency imports its anchor's inflation and interest rate (`fiscal_money_supply_calculation`): no one sets
  the interest rate of a pegged currency, and CWP 1.5 kept the rate it had when the peg began, so countries that
  pegged after a bout of inflation paid 40-60% more on their loans for decades (`interest_rates` adds 1% loan
  interest per point). Independent central banks still settle at high rates where debt is being monetized
  (`money_supply_growth_from_gold`): by 1980 most AI banks with independent policy sit above 20%.
- Only a currency's leading central bank (`central_bank_list`) moves its value: the monthly change, devaluing,
  revaluing and selling foreign reserves (`onaction_ai_sell_foreign_reserves_calculation`, `sell_foreign_reserves`);
  buying a currency moves its leader's. Reserve sales by every other user of a shared currency (most of the world
  uses the dollar) each raised it 1%, so by 1970 the dollar was worth 44 times the median currency instead of about
  twice, and IMF debt, counted in a reserve asset averaged over the members' currencies, cost India 55 times its
  weekly income in repayments.
- The AI buys foreign currency only with its own money (`onaction_ai_buy_foreign_currency_calculation`). CWP 1.5 let
  it spend its treasury plus its credit, but a purchase is a twentieth of the issuer's money supply, which counts the
  issuer's credit, and the 1.14 credit limit is four to nine times 1.5's: the AI borrowed about 650 million for
  reserves by 1948 (CWP 1.5's AI held its reserves almost free of debt, with world debt falling from 84 to 54
  million), and Japan went bankrupt paying twice its income in interest.
- Investment pools are soft-capped at the gold reserves limit (`onaction_investment_pool_softcap`): above it the
  `full_investment_pool` modifier lowers the contribution of every pop type that pays into the pool. Keep its list in
  step with the contributions in the base values of `common/static_modifiers/00_code_static_modifiers.txt`.
- Every country has 50 innovation, 50 more maximum innovation and 25 tech spread of its own (base values, as in
  CWP 1.5 and the base game), which the Schools institution adds to (10, 10 and 5 per level). The technology costs of
  `common/technology/eras` are CWP 1.5's and assume that base: with research left to Schools alone, which the AI
  keeps at level 0 or 1, 67 of 164 countries researched under 5 points a week in 1970 and India, Republican China,
  Egypt and Ethiopia researched nothing from 1950 to 1970.

Housing and healthcare rules:
- CWP 1.5's housing and healthcare are goods again (`common/goods/cwp_housing_healthcare_goods.txt`), priced in each
  market and not traded between markets as in CWP 1.5, with CWP 1.5's needs and amounts for every wealth level added
  to the developers' buy packages (`popneed_housing`, `popneed_healthcare`: healthcare also takes pharmaceuticals and
  a little services).
- Most housing comes, as in CWP 1.5, from the cities and the countryside. CWP 1.5's residential zoning returns to the
  urban centers (`pmg_residential_areas`, `common/production_methods/cwp_residential_zoning.txt`). CWP 1.5's urban
  centers turned services into housing one for one, and their services were in surplus (around 60% below base price
  from 1946 to 1952), so they zoned as far as their urban form allowed. The current urban centers make deposits and the
  service sectors make the services (scarcer, and priced in each state), so zoning adds housing without a trade, as far
  as the urban center's amenities allow in place of CWP 1.5's urban forms (residential zoning with arcades, extensive
  zoning with shopping malls, arcologies with vertical malls and hyperdense urbanism). A level houses 10, 20, 30 or 40,
  two thirds of CWP 1.5's 15 to 60, because a level has 6,000 workers to CWP 1.5's 9,500. Measured against CWP 1.5's
  1950 (176,000 housing a week: 53% zoning, 30% housing buildings, 16% subsistence): CWP 1.5's 30 a level for every
  urban center doubled that and left housing at its floor price; buying the services pinned housing at its ceiling.
  The subsistence buildings house their peasants again (1, 0.75 or 2 a level, the values the developers had left
  commented out as services).
- Housing (`building_housing`) is placed by the game up to the state's housing capacity, which each construction
  sector level raises by 1 (brick and wood, steel frames) or 2 (prefabricated), CWP 1.5's values for the matching
  construction methods: housing grows with the local construction industry. CWP 1.5's default landlord-owned housing
  employed 400 landlords a level, which it still does (aristocrats here, 1.14 having no ownership production methods);
  its owners are the state's investors, as for other private buildings.
- Slums (`building_slums`) are placed by the game up to `state_max_slums` levels
  (`common/script_values/slums_values.txt`): a level per 100,000 people at 60% unemployment or a housing price 70%
  above base in the state's market, fewer below. They hire only the unemployed (peasants, the developers' mapping of
  CWP 1.5's informal workers), supply a little housing and add turmoil and mortality. Neither housing nor slums use
  the state's urbanization (1.14's urban land usage, which kept the game from placing slums at all).
- Hospitals (`building_hospitals`) produce healthcare and lower mortality, with CWP 1.5's five hospital and seven
  treatment methods; CWP 1.5's technologies map onto the developers' tree by era and subject (pre-war healthcare:
  medical science, penicillin: antibiotics, trauma centers: paracetamol, blood typing: immunosuppressants,
  defibrillators: transistors, MRI: third-generation computers, gene therapy and immunotherapy: stem cell therapy, HIV
  treatment: antiviral drugs, cellular reconstruction: genetically modified crops) and CWP 1.5's pop types onto the
  current ones (service workers: clerks, professionals: academics). CWP 1.5's hospitals of 1946 (123 states,
  `common/history/buildings/cwp_hospitals.txt`) start state-owned. The production methods are generated from CWP
  1.5's; their antibiotics method is `pm_antibiotic_treatments` because `pm_antibiotics` is the developers'
  pharmaceutical method.
- Housing and healthcare prices are back in the inflation basket (`inflation_housing_price`,
  `inflation_healthcare_price` in `common/script_values/fiscal_values.txt`), and Housing For The People asks again for
  housing, few slums and cheap housing.
- 1.14's market panel lists only traded and local goods, so housing and healthcare get their own rows under the
  market's goods ("Not Traded Between Markets", `gui/market_panel.gui`: the goods bound to the market with
  `WithMarketContext`, so the rows, tooltips and goods panel show that market's prices). The state panel lists housing
  and slums beside the urban center and financial district (`gui/states_panel_buildings.gui`), since the game leaves
  buildings it places out of the state's building list.
- Measured against CWP 1.5 in observer runs to 1952-1955: the average housing price of 16 major markets stays within
  0.1 of CWP 1.5's (near base; scarcer in Argentina or Egypt, cheaper in the United States), healthcare sits around
  15% above its base price where CWP 1.5's sat around 20% below because pops are wealthier, and the standard of living
  is about 1.5 lower than without housing and healthcare, still above CWP 1.5's.

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
- War support is computed in script (`war_support_change` in `common/script_values/cwp_war_values.txt`, a copy of
  vanilla's war_support_values.txt; keep it in step with vanilla). CWP 1.5 ran the war exhaustion formula every 21
  days instead of vanilla's 7, so `war_support_change` is multiplied by `cwp_war_support_pace` (7/21), and occupation
  enforces war goals at the same pace (`DEFAULT_WAR_GOAL_ENFORCEMENT_FILL_PER_WEEK`/`DEPLETE` in
  `common/defines/cwp_defines.txt`, and the war goal types that set their own `fill_per_week`). Before 1.14 war
  support ran from -100 to 100; thresholds carried over from CWP 1.5 are mapped onto 0..100 as (x + 100) / 2 and
  one-off additions halved. `last_stand` (both Chinas and Indonesia at the start, the Koreas when their war breaks
  out) removed war exhaustion from casualties, which lost battles only amplified in 1.5, so it now also removes the
  war support lost to lost battles.

Subject and decolonization rules:
- Decreasing a subject's autonomy needs the subject's consent, as in CWP 1.5 (`requires_approval` and CWP 1.5's
  acceptance in `common/diplomatic_actions/cwp_subject_interaction_decrease_autonomy.txt`). With the base game's
  instant action the AI turned dominions such as India, Pakistan and New Zealand into puppets within a decade.
- `je_decolonization` (A Fragile Empire) runs its twenty years and the empire's fate is decided by imperial unity at
  the timeout or when unity runs out. CWP 1.5 also completed it when the empire reached superpower rank, which the
  1.14 United Kingdom does in 1947-48, ending the entry (and its India factors, which last until 1956) almost at once.
- A journal entry's progress bar starts from the value of `current_value` when the entry is activated, after its
  `immediate`; an entry that should count from 0 must report 0 until its first update
  (`cwp_decolonization_tracking`).

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
