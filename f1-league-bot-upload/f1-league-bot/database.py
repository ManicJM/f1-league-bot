"""All database access for the F1 league stewarding bot.

Uses SQLite — a single file on disk (data/league.db by default). No separate
database server to install. Every function here is small and does one thing so
the command code stays readable.

Core ideas:
  * A "division" (tier) has its own steward role and its own reports channel.
  * Drivers belong to a division.
  * An incident report -> optional defence -> a steward verdict.
  * A verdict records seconds + penalty points + any ban, referencing a rule.
  * Penalty points are summed per driver, per division, per season, and
    compared against the ban thresholds in rules.py.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    guild_id TEXT NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS divisions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id             TEXT NOT NULL,
    name                 TEXT NOT NULL,
    steward_role_id      TEXT,
    steward_role_ids     TEXT,
    reports_channel_id   TEXT,
    organised_channel_id TEXT,
    decisions_channel_id TEXT,
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS drivers (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id  TEXT NOT NULL,
    user_id   TEXT,
    name      TEXT NOT NULL,
    number    INTEGER,
    team      TEXT,
    gamertag  TEXT,
    platform  TEXT,
    division_id INTEGER,
    active    INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id       TEXT NOT NULL,
    division_id    INTEGER,
    season         INTEGER NOT NULL DEFAULT 1,
    case_number    INTEGER NOT NULL,
    reporter_id    TEXT,
    accused_driver_id INTEGER,
    involved       TEXT,
    lap            TEXT,
    corner         TEXT,
    description    TEXT,
    footage_url    TEXT,
    status         TEXT NOT NULL DEFAULT 'open',  -- open | closed
    organised_channel_id TEXT,
    organised_message_id TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS defences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  INTEGER NOT NULL,
    driver_id    INTEGER,
    submitter_id TEXT,
    description  TEXT,
    footage_url  TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verdicts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      TEXT NOT NULL,
    incident_id   INTEGER,
    division_id   INTEGER,
    season        INTEGER NOT NULL DEFAULT 1,
    driver_id     INTEGER NOT NULL,
    rule_code     TEXT,
    seconds       INTEGER NOT NULL DEFAULT 0,
    points        INTEGER NOT NULL DEFAULT 0,
    ban           TEXT,
    notes         TEXT,
    steward_id    TEXT,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE SET NULL,
    FOREIGN KEY (driver_id)   REFERENCES drivers(id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appeals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     TEXT NOT NULL,
    incident_id  INTEGER,
    driver_id    INTEGER NOT NULL,
    division_id  INTEGER,
    season       INTEGER NOT NULL DEFAULT 1,
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'open',  -- open | upheld | rejected
    created_at   TEXT NOT NULL,
    FOREIGN KEY (driver_id) REFERENCES drivers(id) ON DELETE CASCADE
);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn):
    """Small, safe migrations so existing databases pick up new columns."""
    div_cols = {r["name"] for r in conn.execute("PRAGMA table_info(divisions)").fetchall()}
    if "organised_channel_id" not in div_cols:
        conn.execute("ALTER TABLE divisions ADD COLUMN organised_channel_id TEXT")
    if "steward_role_ids" not in div_cols:
        conn.execute("ALTER TABLE divisions ADD COLUMN steward_role_ids TEXT")
        # carry existing single steward role into the new list
        conn.execute("UPDATE divisions SET steward_role_ids = steward_role_id "
                     "WHERE steward_role_ids IS NULL AND steward_role_id IS NOT NULL")

    inc_cols = {r["name"] for r in conn.execute("PRAGMA table_info(incidents)").fetchall()}
    if "organised_channel_id" not in inc_cols:
        conn.execute("ALTER TABLE incidents ADD COLUMN organised_channel_id TEXT")
    if "organised_message_id" not in inc_cols:
        conn.execute("ALTER TABLE incidents ADD COLUMN organised_message_id TEXT")


# ---------------------------------------------------------------- settings ---
def get_setting(guild_id, key, default=None):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE guild_id=? AND key=?",
            (str(guild_id), key),
        ).fetchone()
    return row["value"] if row else default


def set_setting(guild_id, key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (guild_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value",
            (str(guild_id), key, str(value)),
        )


def current_season(guild_id) -> int:
    return int(get_setting(guild_id, "current_season", "1"))


# --------------------------------------------------------------- divisions ---
def add_division(guild_id, name, steward_role_id, reports_channel_id,
                 organised_channel_id=None, decisions_channel_id=None):
    role_id = str(steward_role_id) if steward_role_id else None
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO divisions (guild_id, name, steward_role_id, steward_role_ids, "
            "reports_channel_id, organised_channel_id, decisions_channel_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET "
            "steward_role_id=excluded.steward_role_id, "
            "steward_role_ids=excluded.steward_role_ids, "
            "reports_channel_id=excluded.reports_channel_id, "
            "organised_channel_id=excluded.organised_channel_id, "
            "decisions_channel_id=excluded.decisions_channel_id",
            (str(guild_id), name, role_id, role_id,
             str(reports_channel_id) if reports_channel_id else None,
             str(organised_channel_id) if organised_channel_id else None,
             str(decisions_channel_id) if decisions_channel_id else None),
        )
        return cur.lastrowid


def get_steward_role_ids(guild_id, division_id):
    """Return the list of steward role IDs (as strings) for a division."""
    div = get_division(guild_id, division_id)
    if not div:
        return []
    try:
        raw = div["steward_role_ids"]
    except (KeyError, IndexError):
        raw = None
    if raw:
        return [x for x in raw.split(",") if x]
    # fall back to the legacy single role if the list is empty
    return [str(div["steward_role_id"])] if div["steward_role_id"] else []


def set_steward_role_ids(guild_id, division_id, ids):
    with get_conn() as conn:
        conn.execute(
            "UPDATE divisions SET steward_role_ids=? WHERE guild_id=? AND id=?",
            (",".join(str(i) for i in ids), str(guild_id), division_id),
        )


def add_steward_role(guild_id, division_id, role_id):
    ids = get_steward_role_ids(guild_id, division_id)
    if str(role_id) not in ids:
        ids.append(str(role_id))
        set_steward_role_ids(guild_id, division_id, ids)
    return ids


def remove_steward_role(guild_id, division_id, role_id):
    ids = [i for i in get_steward_role_ids(guild_id, division_id) if i != str(role_id)]
    set_steward_role_ids(guild_id, division_id, ids)
    return ids


def list_divisions(guild_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM divisions WHERE guild_id=? ORDER BY name", (str(guild_id),)
        ).fetchall()


def get_division(guild_id, division_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM divisions WHERE guild_id=? AND id=?", (str(guild_id), division_id)
        ).fetchone()


def division_for_channel(guild_id, channel_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM divisions WHERE guild_id=? AND reports_channel_id=?",
            (str(guild_id), str(channel_id)),
        ).fetchone()


def find_division(guild_id, ref):
    ref = str(ref).strip()
    with get_conn() as conn:
        if ref.isdigit():
            row = conn.execute(
                "SELECT * FROM divisions WHERE guild_id=? AND id=?", (str(guild_id), int(ref))
            ).fetchone()
            if row:
                return row
        rows = conn.execute(
            "SELECT * FROM divisions WHERE guild_id=? AND LOWER(name) LIKE ?",
            (str(guild_id), f"%{ref.lower()}%"),
        ).fetchall()
    return rows[0] if len(rows) == 1 else None


# ----------------------------------------------------------------- drivers ---
def add_driver(guild_id, name, number, team, gamertag, platform, division_id=None, user_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO drivers (guild_id, user_id, name, number, team, gamertag, platform, division_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), str(user_id) if user_id else None, name, number, team,
             gamertag, platform, division_id),
        )
        return cur.lastrowid


def update_driver(guild_id, driver_id, **fields):
    allowed = {"name", "number", "team", "gamertag", "platform", "division_id", "user_id", "active"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return
    params += [str(guild_id), driver_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE drivers SET {', '.join(sets)} WHERE guild_id=? AND id=?", params)


def list_drivers(guild_id, division_id=None, active_only=True):
    q = ("SELECT d.*, v.name AS division_name FROM drivers d "
         "LEFT JOIN divisions v ON v.id = d.division_id WHERE d.guild_id=?")
    params = [str(guild_id)]
    if division_id is not None:
        q += " AND d.division_id=?"
        params.append(division_id)
    if active_only:
        q += " AND d.active=1"
    q += " ORDER BY (d.number IS NULL), d.number, d.name"
    with get_conn() as conn:
        return conn.execute(q, params).fetchall()


def get_driver(guild_id, driver_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT d.*, v.name AS division_name FROM drivers d "
            "LEFT JOIN divisions v ON v.id = d.division_id "
            "WHERE d.guild_id=? AND d.id=?",
            (str(guild_id), driver_id),
        ).fetchone()


def find_driver(guild_id, ref, division_id=None):
    """Find a driver by number (if ref is digits), by @mention id, or by name."""
    ref = str(ref).strip()
    # strip a Discord mention like <@123> or <@!123>
    mention = ref.replace("<@", "").replace("!", "").replace(">", "")
    with get_conn() as conn:
        if ref.isdigit():
            row = conn.execute(
                "SELECT * FROM drivers WHERE guild_id=? AND number=? AND active=1",
                (str(guild_id), int(ref)),
            ).fetchone()
            if row:
                return row
        if mention.isdigit():
            row = conn.execute(
                "SELECT * FROM drivers WHERE guild_id=? AND user_id=? AND active=1",
                (str(guild_id), mention),
            ).fetchone()
            if row:
                return row
        q = "SELECT * FROM drivers WHERE guild_id=? AND active=1 AND LOWER(name) LIKE ?"
        params = [str(guild_id), f"%{ref.lower()}%"]
        if division_id is not None:
            q += " AND division_id=?"
            params.append(division_id)
        rows = conn.execute(q, params).fetchall()
    return rows[0] if len(rows) == 1 else None


# --------------------------------------------------------------- incidents ---
def next_case_number(guild_id, division_id, season):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(case_number), 0) AS m FROM incidents "
            "WHERE guild_id=? AND division_id IS ? AND season=?",
            (str(guild_id), division_id, season),
        ).fetchone()
    return int(row["m"]) + 1


def add_incident(guild_id, division_id, season, reporter_id, accused_driver_id,
                 involved, lap, corner, description, footage_url):
    case_number = next_case_number(guild_id, division_id, season)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO incidents (guild_id, division_id, season, case_number, reporter_id, "
            "accused_driver_id, involved, lap, corner, description, footage_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), division_id, season, case_number, str(reporter_id) if reporter_id else None,
             accused_driver_id, involved, lap, corner, description, footage_url, now_iso()),
        )
        return cur.lastrowid, case_number


def get_incident(guild_id, division_id, case_number, season):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM incidents WHERE guild_id=? AND division_id IS ? AND case_number=? AND season=?",
            (str(guild_id), division_id, case_number, season),
        ).fetchone()


def get_incident_by_id(guild_id, incident_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM incidents WHERE guild_id=? AND id=?", (str(guild_id), incident_id)
        ).fetchone()


def list_open_incidents(guild_id, division_id, season):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM incidents WHERE guild_id=? AND division_id IS ? AND season=? AND status='open' "
            "ORDER BY case_number",
            (str(guild_id), division_id, season),
        ).fetchall()


def set_incident_status(incident_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE incidents SET status=? WHERE id=?", (status, incident_id))


def set_incident_organised_message(incident_id, channel_id, message_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE incidents SET organised_channel_id=?, organised_message_id=? WHERE id=?",
            (str(channel_id), str(message_id), incident_id),
        )


# ---------------------------------------------------------------- defences ---
def add_defence(incident_id, driver_id, submitter_id, description, footage_url):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO defences (incident_id, driver_id, submitter_id, description, footage_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (incident_id, driver_id, str(submitter_id) if submitter_id else None,
             description, footage_url, now_iso()),
        )


def get_defences(incident_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM defences WHERE incident_id=? ORDER BY id", (incident_id,)
        ).fetchall()


# ---------------------------------------------------------------- verdicts ---
def add_verdict(guild_id, incident_id, division_id, season, driver_id, rule_code,
                seconds, points, ban, notes, steward_id):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO verdicts (guild_id, incident_id, division_id, season, driver_id, rule_code, "
            "seconds, points, ban, notes, steward_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), incident_id, division_id, season, driver_id, rule_code,
             int(seconds), int(points), ban, notes, str(steward_id) if steward_id else None, now_iso()),
        )
        return cur.lastrowid


def get_verdict_for_incident(guild_id, incident_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM verdicts WHERE guild_id=? AND incident_id=? ORDER BY id DESC LIMIT 1",
            (str(guild_id), incident_id),
        ).fetchone()


def driver_points(guild_id, driver_id, division_id, season):
    """Total penalty points for a driver in a division/season."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS pts FROM verdicts "
            "WHERE guild_id=? AND driver_id=? AND division_id IS ? AND season=?",
            (str(guild_id), driver_id, division_id, season),
        ).fetchone()
    return int(row["pts"])


def driver_verdicts(guild_id, driver_id, season=None):
    q = "SELECT * FROM verdicts WHERE guild_id=? AND driver_id=?"
    params = [str(guild_id), driver_id]
    if season is not None:
        q += " AND season=?"
        params.append(season)
    q += " ORDER BY created_at"
    with get_conn() as conn:
        return conn.execute(q, params).fetchall()


def points_board(guild_id, division_id, season):
    with get_conn() as conn:
        return conn.execute(
            "SELECT d.id, d.name, d.number, COALESCE(SUM(v.points),0) AS pts, COUNT(v.id) AS verdicts "
            "FROM drivers d JOIN verdicts v ON v.driver_id = d.id "
            "WHERE d.guild_id=? AND v.division_id IS ? AND v.season=? "
            "GROUP BY d.id HAVING pts > 0 ORDER BY pts DESC",
            (str(guild_id), division_id, season),
        ).fetchall()


# ----------------------------------------------------------------- appeals ---
def add_appeal(guild_id, incident_id, driver_id, division_id, season, reason):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO appeals (guild_id, incident_id, driver_id, division_id, season, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), incident_id, driver_id, division_id, season, reason, now_iso()),
        )
        return cur.lastrowid


def appeals_used(guild_id, driver_id, division_id, season):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM appeals "
            "WHERE guild_id=? AND driver_id=? AND division_id IS ? AND season=?",
            (str(guild_id), driver_id, division_id, season),
        ).fetchone()
    return int(row["c"])


def set_appeal_status(appeal_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE appeals SET status=? WHERE id=?", (status, appeal_id))
