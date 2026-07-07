"""Steward actions: issuing verdicts, viewing penalty points, and appeals."""
import discord
from discord import app_commands
from discord.ext import commands

import database
import rules
from .common import (BRAND, driver_label, resolve_division, is_steward_for,
                     format_penalty, update_organised_card)


async def rule_autocomplete(interaction: discord.Interaction, current: str):
    cur = current.lower()
    out = []
    for r in rules.RULES:
        label = f"{r['code']} — {r['title']}"
        if cur in label.lower():
            out.append(app_commands.Choice(name=label[:100], value=r["code"]))
    return out[:25]


BAN_CHOICES = [
    app_commands.Choice(name="None", value="none"),
    app_commands.Choice(name="Qualifying ban", value="qualifying"),
    app_commands.Choice(name="Race ban", value="race"),
]


class Steward(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    steward = app_commands.Group(name="steward", description="Steward actions")

    @steward.command(name="verdict", description="Issue a verdict on an incident (stack up to 3 rules).")
    @app_commands.describe(
        case="The case number being ruled on",
        rule="The main rulebook code (auto-fills the standard penalty)",
        rule2="A second rule to stack on top (e.g. 3A reckless) — optional",
        rule3="A third rule to stack — optional",
        driver="Who to penalise (defaults to the accused driver in the case)",
        seconds="Override the TOTAL time penalty in seconds",
        points="Override the TOTAL penalty points",
        ban="Add or override a ban outcome",
        final_race="Apply end-of-season scaling (rule 11C: time ×150%, PP-only becomes +5s)",
        notes="Extra notes / reasoning for the write-up",
    )
    @app_commands.autocomplete(rule=rule_autocomplete, rule2=rule_autocomplete, rule3=rule_autocomplete)
    @app_commands.choices(ban=BAN_CHOICES)
    async def verdict(self, interaction: discord.Interaction, case: int, rule: str,
                      rule2: str = None, rule3: str = None,
                      driver: str = None, seconds: int = None, points: int = None,
                      ban: app_commands.Choice[str] = None, final_race: bool = False,
                      notes: str = None):
        gid = interaction.guild_id
        div = resolve_division(interaction)
        if not is_steward_for(interaction, div):
            await interaction.response.send_message(
                "Only this division's stewards (or a server admin) can issue verdicts.", ephemeral=True)
            return
        season = database.current_season(gid)
        inc = database.get_incident(gid, div["id"] if div else None, case, season)
        if not inc:
            await interaction.response.send_message(
                f"No case #{case} found in this division for season {season}.", ephemeral=True)
            return

        # Which driver is being penalised
        if driver:
            pen_driver = database.find_driver(gid, driver)
        else:
            pen_driver = database.get_driver(gid, inc["accused_driver_id"]) if inc["accused_driver_id"] else None
        if not pen_driver:
            await interaction.response.send_message(
                "Couldn't determine which driver to penalise. Pass the `driver` option.", ephemeral=True)
            return

        # Resolve every selected rule.
        selected = []
        for code in (rule, rule2, rule3):
            if not code:
                continue
            r = rules.get_rule(code)
            if not r:
                await interaction.response.send_message(
                    f"Unknown rule code `{code}`. Pick from the autocomplete list.", ephemeral=True)
                return
            selected.append(r)

        # Stack the penalties: sum seconds & points, take the most severe ban.
        ban_rank = {None: 0, "qualifying": 1, "race": 2}
        base_sec = sum(r["seconds"] for r in selected)
        base_pts = sum(r["points"] for r in selected)
        base_ban = None
        for r in selected:
            if ban_rank.get(r["ban"], 0) > ban_rank.get(base_ban, 0):
                base_ban = r["ban"]

        # Overrides replace the stacked totals.
        sec = base_sec if seconds is None else seconds
        pts = base_pts if points is None else points
        ban_val = base_ban
        if ban is not None:
            ban_val = None if ban.value == "none" else ban.value

        # End-of-season scaling (rule 11C)
        scaling_note = ""
        if final_race:
            pre = sec
            sec = round(sec * rules.FINAL_RACE_TIME_MULTIPLIER)
            if pre == 0 and pts > 0:
                sec += rules.FINAL_RACE_PP_ONLY_AS_SECONDS
            scaling_note = " (final-race scaling applied per rule 11C)"

        rule_code_str = " + ".join(r["code"] for r in selected)
        division_id = div["id"] if div else None
        previous = database.driver_points(gid, pen_driver["id"], division_id, season)
        database.add_verdict(gid, inc["id"], division_id, season, pen_driver["id"],
                             rule_code_str, sec, pts, ban_val, notes, interaction.user.id)
        database.set_incident_status(inc["id"], "closed")
        # Fold the decision into the consolidated organised-channel case card.
        full = database.get_incident_by_id(gid, inc["id"])
        await update_organised_card(interaction.guild, gid, div, full)
        new_total = previous + pts
        crossed = rules.ban_thresholds_crossed(previous, new_total)

        # Build the decision write-up
        rules_desc = "\n".join(f"**{r['code']} — {r['title']}**" for r in selected)
        embed = discord.Embed(
            title=f"⚖️ Steward decision — Case #{case}",
            color=BRAND,
            description=rules_desc)
        embed.add_field(name="Driver", value=driver_label(pen_driver), inline=True)
        embed.add_field(name="Penalty (combined)", value=format_penalty(sec, pts, ban_val) + scaling_note, inline=False)
        embed.add_field(name="Penalty points",
                        value=f"{previous} → **{new_total}** (Season {season}, {div['name'] if div else 'division'})",
                        inline=False)
        rule_notes = [f"`{r['code']}` {r['note']}" for r in selected if r["variable"] and r["note"]]
        if rule_notes:
            embed.add_field(name="Rule notes", value="\n".join(rule_notes), inline=False)
        if notes:
            embed.add_field(name="Steward notes", value=notes, inline=False)
        if crossed:
            alert = "\n".join(f"• **{t} PP** → {c}" for t, c in crossed)
            embed.add_field(name="⚠️ Ban threshold reached (rule 11A)", value=alert, inline=False)
        embed.set_footer(text=f"Ruling by {interaction.user.display_name}")

        # Post publicly to the decisions channel if set, otherwise in place.
        posted_to = None
        if div and div["decisions_channel_id"]:
            ch = interaction.guild.get_channel(int(div["decisions_channel_id"]))
            if ch:
                await ch.send(embed=embed)
                posted_to = ch.mention
        await interaction.response.send_message(
            content=(f"Verdict recorded" + (f" and posted to {posted_to}" if posted_to else "") + "."),
            embed=embed, ephemeral=bool(posted_to))

    @steward.command(name="points", description="Show a driver's penalty points and verdict history.")
    @app_commands.describe(driver="Name / number / @mention of the driver")
    async def points(self, interaction: discord.Interaction, driver: str):
        gid = interaction.guild_id
        d = database.find_driver(gid, driver)
        if not d:
            await interaction.response.send_message(
                f"Couldn't find a single driver matching `{driver}`.", ephemeral=True)
            return
        season = database.current_season(gid)
        total = database.driver_points(gid, d["id"], d["division_id"], season)
        verdicts = database.driver_verdicts(gid, d["id"], season)
        embed = discord.Embed(
            title=f"Penalty points — {driver_label(d)}",
            color=BRAND,
            description=f"**{total} PP** this season (S{season})")
        # Show progress toward next threshold
        nxt = next((t for t, _ in rules.PP_THRESHOLDS if t > total), None)
        if nxt:
            _, cons = next((x for x in rules.PP_THRESHOLDS if x[0] == nxt))
            embed.add_field(name="Next threshold",
                            value=f"{nxt - total} PP away from: {cons}", inline=False)
        if verdicts:
            hist = []
            for v in verdicts[-15:]:
                pen = format_penalty(v["seconds"], v["points"], v["ban"])
                hist.append(f"`{v['rule_code'] or '—'}` {pen}")
            embed.add_field(name="Recent verdicts", value="\n".join(hist), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @steward.command(name="board", description="Penalty-point standings for a division this season.")
    async def board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        div = resolve_division(interaction)
        if not div:
            await interaction.response.send_message(
                "Use this in a division's reports channel so I know which board to show.", ephemeral=True)
            return
        season = database.current_season(gid)
        rows = database.points_board(gid, div["id"], season)
        if not rows:
            await interaction.response.send_message(
                f"No penalty points recorded in {div['name']} for season {season}. Clean racing! 🏁",
                ephemeral=True)
            return
        lines = []
        for i, r in enumerate(rows, 1):
            num = f"#{r['number']} " if r["number"] is not None else ""
            lines.append(f"`{r['pts']:>2} PP` {num}{r['name']}  _(from {r['verdicts']} verdict(s))_")
        embed = discord.Embed(
            title=f"Penalty points — {div['name']} (S{season})",
            color=BRAND, description="\n".join(lines))
        embed.set_footer(text="Thresholds: 4=Q ban, 8=Race ban, 12=2nd race ban, 16=removal (rule 11A)")
        await interaction.response.send_message(embed=embed)

    # --------------------------------------------------------------- appeals ---
    appeal = app_commands.Group(name="appeal", description="Appeals (2 per tier per season, rule 23A)")

    @appeal.command(name="file", description="File an appeal against a verdict.")
    @app_commands.describe(case="The case number you're appealing", reason="Why you're appealing")
    async def file(self, interaction: discord.Interaction, case: int, reason: str):
        gid = interaction.guild_id
        div = resolve_division(interaction)
        season = database.current_season(gid)
        d = database.find_driver(gid, str(interaction.user.id))
        if not d:
            await interaction.response.send_message(
                "You need a registered driver profile to file an appeal (`/driver register`).", ephemeral=True)
            return
        division_id = div["id"] if div else d["division_id"]
        used = database.appeals_used(gid, d["id"], division_id, season)
        if used >= 2:
            await interaction.response.send_message(
                "You've used both of your appeals for this tier this season (rule 23A). No more are available.",
                ephemeral=True)
            return
        inc = database.get_incident(gid, division_id, case, season)
        database.add_appeal(gid, inc["id"] if inc else None, d["id"], division_id, season, reason)
        embed = discord.Embed(
            title=f"📨 Appeal filed — Case #{case}",
            color=discord.Color.gold(),
            description=reason)
        embed.add_field(name="Driver", value=driver_label(d), inline=True)
        embed.add_field(name="Appeals used", value=f"{used + 1}/2", inline=True)
        embed.set_footer(text="Reminder: a pointless appeal costs +1 PP (23D); a unanimous rejection "
                              "costs +1 PP and loss of decision (23E). Appeals close 24h after the ruling (23E).")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Steward(bot))
