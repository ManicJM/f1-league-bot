"""Incident reports and defences.

Flow:
  /incident report against:<driver>   -> opens a form (lap, corner, description, footage)
                                          -> posts an incident card into the division channel
  /incident defend case:<n>            -> opens a form for the defence (description + footage)
  /incident pending                    -> lists open incidents in this division
  /incident view case:<n>              -> shows a specific incident + any defences

Enforces the minimum report template from rule 15K: accused tagged, lap,
description and footage link are required. Footage must be a real link
(phone footage is not accepted — rule 15C).
"""
import discord
from discord import app_commands
from discord.ext import commands

import database
from .common import (BRAND, driver_label, resolve_division,
                     render_case_embed, update_organised_card)


async def driver_autocomplete(interaction: discord.Interaction, current: str):
    div = resolve_division(interaction)
    division_id = div["id"] if div else None
    drivers = database.list_drivers(interaction.guild_id, division_id=division_id)
    out = []
    for d in drivers:
        label = f"#{d['number']} {d['name']}" if d["number"] is not None else d["name"]
        if current.lower() in label.lower():
            out.append(app_commands.Choice(name=label[:100], value=str(d["id"])))
    return out[:25]


class ReportModal(discord.ui.Modal, title="Incident report"):
    lap = discord.ui.TextInput(label="Lap", placeholder="e.g. 12", required=True, max_length=20)
    corner = discord.ui.TextInput(label="Corner (optional)", required=False, max_length=40)
    description = discord.ui.TextInput(
        label="Brief description of what happened",
        style=discord.TextStyle.paragraph, required=True, max_length=1500,
        placeholder="Stick to the facts — no emotional or antagonising comments (rules 6F / 17F).")
    footage = discord.ui.TextInput(
        label="Report footage link",
        placeholder="Paste your footage link (rule 15C: console/PC/Twitch/YouTube — no phone footage)",
        required=True, max_length=300)

    def __init__(self, division, accused):
        super().__init__()
        self.division = division
        self.accused = accused

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        season = database.current_season(gid)
        division_id = self.division["id"] if self.division else None
        incident_id, case_number = database.add_incident(
            gid, division_id, season, interaction.user.id,
            self.accused["id"] if self.accused else None,
            None, str(self.lap), str(self.corner) or None,
            str(self.description), str(self.footage),
        )
        embed = discord.Embed(
            title=f"🟠 Incident report — Case #{case_number}",
            color=discord.Color.orange(),
            description=str(self.description),
        )
        embed.add_field(name="Reported by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Accused", value=driver_label(self.accused), inline=True)
        embed.add_field(name="Division", value=self.division["name"] if self.division else "—", inline=True)
        embed.add_field(name="Lap", value=str(self.lap), inline=True)
        embed.add_field(name="Corner", value=str(self.corner) or "—", inline=True)
        embed.add_field(name="Footage", value=str(self.footage), inline=False)
        embed.set_footer(text=f"Season {season} • Case #{case_number} • Defend with /incident defend")

        # 1) Public report card in the reports channel (fallback: current channel).
        ping = None
        if self.accused and self.accused["user_id"]:
            ping = f"<@{self.accused['user_id']}> you have been reported — you may submit a defence."
        guild = interaction.guild
        reports_ch = None
        if self.division and self.division["reports_channel_id"]:
            reports_ch = guild.get_channel(int(self.division["reports_channel_id"]))
        if reports_ch is None:
            reports_ch = interaction.channel
        await reports_ch.send(content=ping, embed=embed)

        # 2) Consolidated case card in the stewards' organised channel.
        full = database.get_incident_by_id(interaction.guild_id, incident_id)
        org = await update_organised_card(guild, interaction.guild_id, self.division, full)

        where = reports_ch.mention + (f" + {org.mention} (stewards)" if org else "")
        await interaction.response.send_message(
            f"✅ Report submitted as **Case #{case_number}** "
            f"in **{self.division['name'] if self.division else 'this channel'}** → {where}.",
            ephemeral=True)


class DefendModal(discord.ui.Modal, title="Incident defence"):
    description = discord.ui.TextInput(
        label="Your defence (facts only)",
        style=discord.TextStyle.paragraph, required=True, max_length=1500)
    footage = discord.ui.TextInput(
        label="Defence footage link (1st-person POV)",
        placeholder="Paste your POV footage link — primary source required (rule 17D)",
        required=True, max_length=300)

    def __init__(self, incident, driver):
        super().__init__()
        self.incident = incident
        self.driver = driver

    async def on_submit(self, interaction: discord.Interaction):
        database.add_defence(
            self.incident["id"], self.driver["id"] if self.driver else None,
            interaction.user.id, str(self.description), str(self.footage))
        # 1) Public defence card in the reports channel (fallback: current channel).
        embed = discord.Embed(
            title=f"🔵 Defence — Case #{self.incident['case_number']}",
            color=discord.Color.blue(), description=str(self.description))
        embed.add_field(name="Defended by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Footage", value=str(self.footage), inline=False)
        guild = interaction.guild
        division = None
        if self.incident["division_id"]:
            division = database.get_division(interaction.guild_id, self.incident["division_id"])
        reports_ch = None
        if division and division["reports_channel_id"]:
            reports_ch = guild.get_channel(int(division["reports_channel_id"]))
        if reports_ch is None:
            reports_ch = interaction.channel
        await reports_ch.send(embed=embed)

        # 2) Fold the defence into the consolidated organised-channel card.
        full = database.get_incident_by_id(interaction.guild_id, self.incident["id"])
        org = await update_organised_card(guild, interaction.guild_id, division, full)

        where = reports_ch.mention + (f" + updated the {org.mention} case card" if org else "")
        await interaction.response.send_message(f"✅ Defence submitted → {where}.", ephemeral=True)


class Incidents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    incident = app_commands.Group(name="incident", description="Report and defend incidents")

    @incident.command(name="report", description="Report an incident against another driver.")
    @app_commands.describe(against="The driver you are reporting (name / number)")
    @app_commands.autocomplete(against=driver_autocomplete)
    async def report(self, interaction: discord.Interaction, against: str):
        div = resolve_division(interaction)
        if not div:
            await interaction.response.send_message(
                "I can't tell which division this belongs to. Use this command in your division's "
                "reports channel, or ask an admin to register your driver profile with `/driver register`.",
                ephemeral=True)
            return
        accused = database.find_driver(interaction.guild_id, against, division_id=div["id"]) \
            or database.find_driver(interaction.guild_id, against)
        if not accused:
            await interaction.response.send_message(
                f"Couldn't find a driver matching `{against}`. Make sure they're registered "
                f"(`/driver register`). Rule 15K requires the reported driver to be tagged.",
                ephemeral=True)
            return
        await interaction.response.send_modal(ReportModal(div, accused))

    @incident.command(name="defend", description="Submit a defence for an incident reported against you.")
    @app_commands.describe(case="The case number to defend")
    async def defend(self, interaction: discord.Interaction, case: int):
        div = resolve_division(interaction)
        gid = interaction.guild_id
        season = database.current_season(gid)
        inc = database.get_incident(gid, div["id"] if div else None, case, season)
        if not inc:
            await interaction.response.send_message(
                f"No open case #{case} found in this division for season {season}.", ephemeral=True)
            return
        driver = database.find_driver(gid, str(interaction.user.id))
        await interaction.response.send_modal(DefendModal(inc, driver))

    @incident.command(name="pending", description="List open incidents in this division.")
    async def pending(self, interaction: discord.Interaction):
        div = resolve_division(interaction)
        gid = interaction.guild_id
        season = database.current_season(gid)
        incs = database.list_open_incidents(gid, div["id"] if div else None, season)
        if not incs:
            await interaction.response.send_message("No open incidents. 🎉", ephemeral=True)
            return
        lines = []
        for i in incs:
            accused = database.get_driver(gid, i["accused_driver_id"]) if i["accused_driver_id"] else None
            lines.append(f"**#{i['case_number']}** — vs {driver_label(accused)} (lap {i['lap']})")
        embed = discord.Embed(
            title=f"Open incidents — {div['name'] if div else 'this channel'} (S{season})",
            color=BRAND, description="\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @incident.command(name="view", description="View an incident and any defences.")
    @app_commands.describe(case="The case number to view")
    async def view(self, interaction: discord.Interaction, case: int):
        div = resolve_division(interaction)
        gid = interaction.guild_id
        season = database.current_season(gid)
        inc = database.get_incident(gid, div["id"] if div else None, case, season)
        if not inc:
            await interaction.response.send_message(
                f"No case #{case} found in this division for season {season}.", ephemeral=True)
            return
        embed = render_case_embed(gid, inc)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Incidents(bot))
