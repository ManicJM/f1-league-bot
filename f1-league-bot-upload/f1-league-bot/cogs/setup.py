"""Server setup: divisions (tiers) and season management.

Only members with 'Manage Server' permission can use these commands.
"""
import discord
from discord import app_commands
from discord.ext import commands

import database
from .common import BRAND


async def division_autocomplete(interaction: discord.Interaction, current: str):
    divs = database.list_divisions(interaction.guild_id)
    return [
        app_commands.Choice(name=d["name"], value=str(d["id"]))
        for d in divs if current.lower() in d["name"].lower()
    ][:25]


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    division = app_commands.Group(
        name="division",
        description="Set up divisions/tiers and their stewards",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @division.command(name="add", description="Create or update a division (tier).")
    @app_commands.describe(
        name="Division name, e.g. 'Masters' or 'Tier 1'",
        steward_role="The role whose members can rule on this division's incidents",
        reports_channel="Where drivers submit reports (and get their confirmation)",
        organised_channel="The stewards' channel where this tier's incidents are discussed (e.g. #organised-incidents-masters)",
        decisions_channel="Optional: a public channel to post steward decisions to",
    )
    async def add(self, interaction: discord.Interaction, name: str,
                  steward_role: discord.Role, reports_channel: discord.TextChannel,
                  organised_channel: discord.TextChannel = None,
                  decisions_channel: discord.TextChannel = None):
        database.add_division(
            interaction.guild_id, name, steward_role.id, reports_channel.id,
            organised_channel.id if organised_channel else None,
            decisions_channel.id if decisions_channel else None,
        )
        embed = discord.Embed(
            title="✅ Division saved",
            color=BRAND,
            description=(
                f"**{name}**\n"
                f"Stewards: {steward_role.mention}\n"
                f"Reports channel: {reports_channel.mention}\n"
                f"Organised (stewards) channel: {organised_channel.mention if organised_channel else '_none_'}\n"
                f"Decisions channel: {decisions_channel.mention if decisions_channel else '_none_'}"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @division.command(name="addsteward", description="Add another steward role to a tier.")
    @app_commands.describe(division="The tier", role="The role to add as stewards")
    @app_commands.autocomplete(division=division_autocomplete)
    async def addsteward(self, interaction: discord.Interaction, division: str, role: discord.Role):
        gid = interaction.guild_id
        div = database.find_division(gid, division)
        if not div:
            await interaction.response.send_message(
                "Couldn't find that division. Try `/division list`.", ephemeral=True)
            return
        ids = database.add_steward_role(gid, div["id"], role.id)
        mentions = ", ".join(f"<@&{r}>" for r in ids)
        await interaction.response.send_message(
            f"✅ Stewards for **{div['name']}** are now: {mentions}", ephemeral=True)

    @division.command(name="removesteward", description="Remove a steward role from a tier.")
    @app_commands.describe(division="The tier", role="The role to remove")
    @app_commands.autocomplete(division=division_autocomplete)
    async def removesteward(self, interaction: discord.Interaction, division: str, role: discord.Role):
        gid = interaction.guild_id
        div = database.find_division(gid, division)
        if not div:
            await interaction.response.send_message(
                "Couldn't find that division. Try `/division list`.", ephemeral=True)
            return
        ids = database.remove_steward_role(gid, div["id"], role.id)
        mentions = ", ".join(f"<@&{r}>" for r in ids) if ids else "_none left_"
        await interaction.response.send_message(
            f"✅ Stewards for **{div['name']}** are now: {mentions}", ephemeral=True)

    @division.command(name="list", description="List all divisions and their settings.")
    async def list_divisions(self, interaction: discord.Interaction):
        divs = database.list_divisions(interaction.guild_id)
        if not divs:
            await interaction.response.send_message(
                "No divisions set up yet. Use `/division add` to create one.", ephemeral=True)
            return
        lines = []
        for d in divs:
            role_ids = database.get_steward_role_ids(interaction.guild_id, d["id"])
            roles = ", ".join(f"<@&{r}>" for r in role_ids) if role_ids else "_no roles_"
            chan = f"<#{d['reports_channel_id']}>" if d["reports_channel_id"] else "_no channel_"
            org = f" · organised <#{d['organised_channel_id']}>" if d["organised_channel_id"] else ""
            dec = f" · decisions <#{d['decisions_channel_id']}>" if d["decisions_channel_id"] else ""
            lines.append(f"**{d['name']}** (id {d['id']}): stewards {roles}, reports {chan}{org}{dec}")
        embed = discord.Embed(title="Divisions", color=BRAND, description="\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    season = app_commands.Group(
        name="season",
        description="Manage the current season",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @season.command(name="show", description="Show the current season number.")
    async def season_show(self, interaction: discord.Interaction):
        s = database.current_season(interaction.guild_id)
        await interaction.response.send_message(
            f"Current season: **{s}**. Penalty points are tracked per season.", ephemeral=True)

    @season.command(name="set", description="Set the current season number (starts fresh penalty points).")
    @app_commands.describe(number="The new season number")
    async def season_set(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 999]):
        old = database.current_season(interaction.guild_id)
        database.set_setting(interaction.guild_id, "current_season", number)
        await interaction.response.send_message(
            f"Season changed from **{old}** to **{number}**. "
            f"Penalty points now count against season {number} (per rule 11B, points reset each season).",
            ephemeral=True)


async def setup(bot):
    await bot.add_cog(Setup(bot))
