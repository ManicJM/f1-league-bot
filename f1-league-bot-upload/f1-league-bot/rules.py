"""The league's penalty catalogue, encoded from the official rulebook.

Each rule has:
  code      - the rulebook reference, e.g. "3C"
  title     - short description
  category  - grouping (Qualifying, Race, Safety Car, ...)
  seconds   - standard time penalty in seconds (0 if none / not a time pen)
  points    - standard penalty points (0 if none)
  ban       - standard ban outcome: None | "qualifying" | "race"
  variable  - True if the penalty escalates/depends on circumstances; the
              `note` explains it and the steward sets the final penalty.
  note      - extra guidance shown to the steward

When a steward issues a verdict they pick a code and the bot pre-fills
`seconds` and `points`. Per rule 11B these are baselines and the steward can
override them. To change a penalty, edit it here — no code changes needed.

Penalty-point ban thresholds (rule 11A), per division per season:
  4 PP  -> qualifying ban
  8 PP  -> race ban
  12 PP -> second race ban
  16 PP -> removal from the tier (admins/head stewards review)
"""

PP_THRESHOLDS = [
    (4, "Qualifying ban"),
    (8, "Race ban"),
    (12, "Second race ban"),
    (16, "Removal from the tier (admins/head stewards to review)"),
]

# End-of-season modifiers (rules 11C, 15M)
FINAL_RACE_TIME_MULTIPLIER = 1.5          # time penalties applied at 150%
FINAL_RACE_PP_ONLY_AS_SECONDS = 5         # a PP-only penalty becomes 5s
NO_FOOTAGE_FINAL_RACE_MULTIPLIER = 2.0    # 200% + loss of decision


def _r(code, title, category, seconds=0, points=0, ban=None, variable=False, note=""):
    return {
        "code": code, "title": title, "category": category,
        "seconds": seconds, "points": points, "ban": ban,
        "variable": variable, "note": note,
    }


RULES = [
    # ---------------------------------------------------------- QUALIFYING ---
    _r("1A", "Impeding a flying lap", "Qualifying", 5, 2,
       note="Includes anything from sector 3 of an outlap onwards."),
    _r("1B", "Impeding a flying lap causing retirement", "Qualifying", 10, 2),
    _r("1C", "AI mode incident during qualifying", "Qualifying", 0, 1,
       note="AI mode allowed but driver is responsible for the car's actions."),

    # ------------------------------------------------------- FORMATION LAP ---
    _r("2A", "Overtaking on the formation lap", "Formation Lap", 0, 1),
    _r("2B", "Not staying within 10 car lengths on formation lap", "Formation Lap", 0, 2,
       note="Stewards consider whether the leader was significantly faster."),
    _r("2C", "Contact causing a DQ/reset to grid", "Formation Lap", 0, 1),
    _r("2D", "AI mode incident on the formation lap", "Formation Lap", 0, 1),
    _r("2E", "Formation lap etiquette breach", "Formation Lap", 0, 2, variable=True,
       note="1st: 2 PP | 2nd: Qualifying ban | 3rd: Race ban. Applies across the server, not just race day."),

    # --------------------------------------------------------------- RACE ---
    _r("3A", "Reckless driving (additional penalty)", "Race", 5, 1,
       note="Applied on top of another incident penalty when driving is reckless."),
    _r("3B", "Causing a collision — no damage", "Race", 5, 1),
    _r("3C", "Causing a collision — with damage", "Race", 10, 2),
    _r("3C.1", "Collision causing unrepairable damage (add-on)", "Race", 0, 1,
       note="Additional +1 PP on top of 3C when damage is unrepairable in the pits."),
    _r("3D", "Incident affecting two or more drivers", "Race", 10, 3,
       note="Auto-upgrade: 10s + 3 PP when an incident affects 2+ drivers."),
    _r("3E", "Causing a collision resulting in a DNF", "Race", 10, 4, variable=True,
       note="10s + 4 PP. For multiple DNFs: +1 PP per extra DNF."),
    _r("3F", "Blocking / moving under braking", "Race", 0, 1),
    _r("3G", "Illegal overtake — give back then immediately retake", "Race", 5, 1),
    _r("3H", "Returning to track in an unsafe manner", "Race", 5, 2),
    _r("3I", "Ignoring blue flags", "Race", 0, 0, ban="qualifying", variable=True,
       note="1st: Qualifying ban | 2nd: Race ban."),
    _r("3J", "Retiring on track without triggering SC/VSC", "Race", 5, 2, variable=True,
       note="Pause-menu retire, no SC/VSC: 5s next race + 2 PP. Intentional wall crash, no SC/VSC: 10s next race + 2 PP. "
            "Pause/intentional crash that DOES trigger SC/VSC: Race ban."),
    _r("3K", "AI mode incident during racing", "Race", 0, 0, variable=True,
       note="Head stewards to advise on the penalty."),
    _r("3L", "No reset to track", "Race", 5, 1),
    _r("3M", "Unsportsmanlike behaviour", "Race", 0, 0, ban="race", variable=True,
       note="1st: Race ban | 2nd: potential removal from server (admins/head stewards review)."),
    _r("3N", "Time wasting report", "Race", 0, 1,
       note="Applied when a report is rejected by head stewards as time-wasting."),
    _r("3O", "Holding up drivers in the pit lane", "Race", 5, 2),
    _r("3P", "Dangerous DRS chicken", "Race", 10, 1, variable=True,
       note="10s + 1 PP (no damage) | 10s + 2 PP (damage) | 10s + 4 PP (retirement)."),
    _r("3Q", "Pushing a driver off track (loss of time/positions)", "Race", 5, 1),
    _r("3R", "Driving standards warning", "Race", 0, 0, variable=True,
       note="1st: warning (strike) | 2nd and every offence after: 5s + 1 PP."),
    _r("3S", "Forcing a driver off track / leaving track for advantage", "Race", 5, 1),
    _r("3T", "Time loss without damage (add-on)", "Race", 5, 0,
       note="Additional 5s on top of 3B if time loss to another driver is >= 5s without damage."),

    # ---------------------------------------------------------- SAFETY CAR ---
    _r("4A", "Overtaking under SC and not returning position", "Safety Car", 5, 2),
    _r("4B", "Causing an incident as leader on SC restart", "Safety Car", 5, 1),
    _r("4C", "Colliding with the car in front under SC", "Safety Car", 10, 2),
    _r("4D", "Failing to remain single file under SC", "Safety Car", 10, 2),
    _r("4E", "Failing to remain within 10 car lengths under SC", "Safety Car", 5, 2),
    _r("4F", "Passing on the 'Pass driver' prompt under SC", "Safety Car", 10, 2,
       note="Ignore the prompt unless the car is a crashed vehicle."),
    _r("4G", "AI mode incident under SC/VSC", "Safety Car", 0, 1),

    # ------------------------------------------------------ PENALTY REMOVAL ---
    _r("5F", "Requesting removal of a clear driver-error penalty", "Penalty Removal", 0, 1,
       note="Falls under time wasting."),

    # -------------------------------------------------- SERVER / ETIQUETTE ---
    _r("6A", "Abusive language / derogatory comments", "Server Etiquette", 0, 4, ban="qualifying", variable=True,
       note="1st: 4 PP + qualifying ban next race | 2nd: permanent removal from server."),
    _r("6C", "Arguing post-race about on-track incidents", "Server Etiquette", 0, 1),
    _r("6G", "Braking marker interference", "Server Etiquette", 0, 0, variable=True,
       note="Treated as unsportsmanlike (see 3M) unless clearly unintentional/unavoidable. Zero tolerance."),

    # ------------------------------------------------------- REPUTATION ------
    _r("12A", "Bringing the league's reputation into disrepute", "Conduct", 0, 0, ban="qualifying", variable=True,
       note="1st: Qualifying ban | 2nd: removal from server. Amendable by admins."),

    # ---------------------------------------------------- ENGINE (DTS) -------
    _r("13A", "3 DNFs in a season (DTS only)", "Conduct", 0, 0, ban="qualifying", variable=True,
       note="Qualifying ban served on next checked-in race, applied every 3rd DNF."),

    # ------------------------------------------------------------ APPEALS ----
    _r("23D", "Pointless appeal", "Appeals", 0, 1,
       note="Additional 1 PP if an appeal is deemed pointless."),
    _r("23E", "Unanimous rejected appeal", "Appeals", 0, 1, variable=True,
       note="Unanimous rejection: +1 PP and loss of decision. Split decision: loss of an appeal, penalty unchanged, no extra PP."),

    # ---------------------------------------------------------- TEMP RULES ---
    _r("24A", "Crossing solid white line on pit entry/exit for advantage", "Temp Rule", 10, 2, variable=True,
       note="1st & 2nd offence: 10s + 2 PP | 3rd offence onwards: Race ban."),
]

# Fast lookup by code (case-insensitive)
_BY_CODE = {r["code"].upper(): r for r in RULES}


def get_rule(code):
    return _BY_CODE.get(str(code).upper().strip())


def all_codes():
    return [r["code"] for r in RULES]


def ban_thresholds_crossed(previous_total, new_total):
    """Return the list of (threshold, consequence) newly reached by going from
    previous_total to new_total penalty points."""
    return [(t, c) for (t, c) in PP_THRESHOLDS if previous_total < t <= new_total]
