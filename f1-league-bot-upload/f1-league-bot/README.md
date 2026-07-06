# 🏁 F1 League Stewarding Bot

A Discord bot that runs the **stewarding** side of your F1 league — incident
reports, defences, steward verdicts, and automatic **penalty-point tracking**
with ban thresholds — plus a **driver directory**. It's built to sit alongside
the FGC app (which handles standings, stats and check-ins), filling the gaps
FGC doesn't cover.

Everything is driven by *your* rulebook: the full penalty catalogue (rule codes
`1A`, `3C`, `4E`, `24A`, …) is encoded in `rules.py`, so when a steward picks a
rule the standard penalty (seconds + penalty points) is filled in automatically.

---

## What it does

**Divisions** — each tier has its own steward role and up to three channels: a
**reports** channel (where drivers submit), an **organised** channel (the
stewards' private working channel where that tier's incidents are discussed,
e.g. `#organised-incidents-masters`), and an optional **decisions** channel
(public rulings). Reports and verdicts automatically route to the right
division, and only that division's stewards can rule on its incidents.

**Incident reports** — a driver runs `/incident report against:<driver>` in
their division channel and fills in a short form (lap, corner, description,
footage link). The form collects the fields your template requires (rule 15K)
and reminds the driver of the footage rules (15C), but it does **not** try to
verify the footage itself — judging whether footage is valid (e.g. rejecting
phone footage) stays with the stewards, since that can't be checked reliably by
a bot. The report is confirmed in the reports
channel with the accused pinged, and a **single consolidated case card** is
posted into the tier's organised channel for the stewards. As defences come in
and a verdict is issued, that same card is **edited in place** — so the report,
every defence, and the final decision always sit together in one message for
easy stewarding, instead of being scattered across the channel.

**Defences** — the accused runs `/incident defend case:<n>` to add their POV
footage and explanation.

**Verdicts** — a steward runs `/steward verdict case:<n> rule:<code>`. The bot
pre-fills the standard penalty from your rulebook, lets the steward override it
(rule 11B says penalties are baselines), applies end-of-season scaling on
request (rule 11C), records it, closes the case, and posts a clean write-up to
your decisions channel.

**Penalty points** — tracked per driver, per division, per season. The bot
warns stewards the moment a verdict pushes a driver across a ban threshold:

| Points | Consequence (rule 11A) |
|-------:|------------------------|
| 4 PP   | Qualifying ban |
| 8 PP   | Race ban |
| 12 PP  | Second race ban |
| 16 PP  | Removal from the tier |

Points reset when you start a new season (`/season set`) and follow a driver if
they move division (rule 11D).

**Appeals** — `/appeal file` enforces your 2-per-tier-per-season limit (rule 23A).

---

## Commands at a glance

**Admin (needs "Manage Server")**
- `/division add name:<> steward_role:<> reports_channel:<> [organised_channel:<>] [decisions_channel:<>]`
- `/division list`
- `/season show` · `/season set number:<>`

**Directory**
- `/driver register name:<> [number] [division] [team] [gamertag] [platform] [member]`
- `/driver list [division]` · `/driver profile driver:<>` · `/driver edit driver:<> …`

**Incidents**
- `/incident report against:<driver>` (opens a form)
- `/incident defend case:<n>` (opens a form)
- `/incident pending` · `/incident view case:<n>`

**Stewards**
- `/steward verdict case:<n> rule:<code> [driver] [seconds] [points] [ban] [final_race] [notes]`
- `/steward points driver:<>` · `/steward board`
- `/appeal file case:<n> reason:<>`

---

## Setup — step by step (no experience needed)

### 1. Create the bot on Discord
1. Go to the **Discord Developer Portal**: https://discord.com/developers/applications
2. Click **New Application**, give it a name (e.g. "League Stewards"), and **Create**.
3. In the left menu click **Bot**, then **Reset Token** → **Copy**. This long
   string is your `DISCORD_TOKEN`. Keep it secret — anyone with it controls your bot.
4. Scroll down to **Privileged Gateway Intents**. You do **not** need any of them
   for this bot (it uses slash commands), so you can leave them off.

### 2. Invite the bot to your server
1. In the left menu go to **OAuth2 → URL Generator**.
2. Under **Scopes** tick **`bot`** and **`applications.commands`**.
3. Under **Bot Permissions** tick: **Send Messages**, **Embed Links**,
   **Read Message History**, and **Mention Everyone** (needed to ping the accused driver).
4. Copy the generated URL at the bottom, open it in your browser, choose your
   server, and click **Authorize**.

### 3. Get your Server ID
1. In Discord: **User Settings → Advanced → Developer Mode** → turn it **on**.
2. Right-click your **server icon → Copy Server ID**. This is your `GUILD_ID`.
   (Setting this makes your slash commands appear instantly.)

### 4. Put your secrets in the `.env` file
1. In the bot folder, make a copy of `.env.example` and name the copy **`.env`**.
2. Open `.env` and paste your values:
   ```
   DISCORD_TOKEN=your-token-here
   GUILD_ID=your-server-id-here
   ```

### 5. Install and run
You need **Python 3.10 or newer**. Check with `python --version` (or `python3`).

```bash
# from inside the f1-league-bot folder
pip install -r requirements.txt
python bot.py
```

When it works you'll see `Logged in as ...` and `Synced N commands`. Your slash
commands are now live in your server. Leave this window open — the bot only runs
while the program is running (see Hosting below to keep it online 24/7).

### 6. First-time configuration in Discord
Run these once, in your server:
```
/division add  name: Masters  steward_role: @Masters Stewards  reports_channel: #masters-reports  organised_channel: #organised-incidents-masters  decisions_channel: #masters-decisions
/division add  name: Tier 1   steward_role: @Tier 1 Stewards   reports_channel: #t1-reports       organised_channel: #organised-incidents-t1
/season set    number: 1
```
Then register drivers with `/driver register`, and you're ready to take reports.

---

## Keeping it online 24/7 (hosting)

Running `python bot.py` on your own PC is perfect for testing, but the bot stops
when you close it or shut down. To keep it always on, host it somewhere:

- **A Raspberry Pi or an old PC** left running at home — free, full control.
- **A cloud host** like Railway, Render, or a small VPS (e.g. a €4/mo box).
  Upload the folder, set `DISCORD_TOKEN` and `GUILD_ID` as environment
  variables, and run `python bot.py`.

**Important about your data:** all league data lives in the single file
`data/league.db`. Back it up regularly. On hosts with "ephemeral" storage
(some free tiers wipe files on restart), attach a **persistent volume** for the
`data/` folder, or your penalty points will reset unexpectedly.

---

## Customising the rules

Open **`rules.py`**. Every offence is one line, for example:

```python
_r("3C", "Causing a collision — with damage", "Race", 10, 2),
#     code                  title              category  secs  pp
```

To change a penalty, edit the numbers. To add a new rule, copy a line and give
it a new code. Ban thresholds live at the top of the file in `PP_THRESHOLDS`.
No other code needs to change — the verdict command picks these up automatically.

---

## Troubleshooting

- **"No Discord token found"** — you haven't created `.env` yet, or the token line is wrong. See step 4.
- **Slash commands don't appear** — make sure `GUILD_ID` is set (step 3) and you invited the bot with the `applications.commands` scope (step 2).
- **Bot can't ping the accused driver** — give it the "Mention Everyone" permission (step 2), and make sure the driver was registered with a linked member.
- **"I can't tell which division this belongs to"** — run the command in that division's reports channel, or register the driver's profile with a division.
