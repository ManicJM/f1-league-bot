"""Driver directory: registration, roster, profiles."""
import discord
from discord import app_commands
from discord.ext import commands

import database
from .common import BRAND, driver_label


PLATFORMS = [
    app_commands.Choice(name="PC", value="PC"),
    app_commands.Choice(name="PlayStation", value="PlayStation"),
    app_commands.Choice(name="Xbox", value="Xbox"),
]


async def division_autocomplete(interaction: discord.Interaction, current: str):
    divs = database.list_divisions(interaction.guild_id)
    return [
        app_commands.Choice(name=d["name"], value=str(d["id"]))
        for d in divs if current.lower() in d["name"].lower()
    ][:25]


class Drivers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    driver = app_commands.Group(name="driver", description="Driver directory")

    @driver.command(name="register", description="Register a driver — just their @ and division.")
    @app_commands.describe(
        member="The driver (pick their Discord @)",
        division="Which division/tier they race in",
    )
    @app_commands.autocomplete(division=division_autocomplete)
    async def register(self, interaction: discord.Interaction,
                       member: discord.Member, division: str):
        gid = interaction.guild_id
        div = database.find_division(gid, division)
        if not div:
            await interaction.response.send_message(
                "Couldn't find that division. Pick one from the list, or set it up first with `/division add`.",
                ephemeral=True)
            return
        # The driver's name is taken from their Discord display name automatically.
        existing = database.find_driver(gid, str(member.id))
        if existing:
            database.update_driver(gid, existing["id"], division_id=div["id"], name=member.display_name)
            action = "updated"
        else:
            database.add_driver(gid, member.display_name, None, None, None, None,
                                division_id=div["id"], user_id=member.id)
            action = "registered"
        embed = discord.Embed(title=f"✅ Driver {action}", color=BRAND)
        embed.add_field(name="Driver", value=member.mention, inline=True)
        embed.add_field(name="Division", value=div["name"], inline=True)
        await interaction.response.send_message(embed=embed)

    @driver.command(name="list", description="Show the driver roster (optionally for one division).")
    @app_commands.describe(division="Filter to a division/tier")
    @app_commands.autocomplete(division=division_autocomplete)
    async def list_drivers(self, interaction: discord.Interaction, division: str = None):
        gid = interaction.guild_id
        division_id = int(division) if division and division.isdigit() else None
        drivers = database.list_drivers(gid, division_id=division_id)
        if not drivers:
            await interaction.response.send_message("No drivers registered yet.", ephemeral=True)
            return
        lines = []
        for d in drivers:
            num = f"`#{d['number']:>2}`" if d["number"] is not None else "`  —`"
            team = f" — {d['team']}" if d["team"] else ""
            divn = f" _{d['division_name']}_" if d["division_name"] else ""
            lines.append(f"{num} **{d['name']}**{team}{divn}")
        title = "Driver roster"
        if division_id:
            div = database.get_division(gid, division_id)
            if div:
                title += f" — {div['name']}"
        # Discord embed descriptions cap at 4096 chars; chunk if needed.
        chunks, cur = [], ""
        for line in lines:
            if len(cur) + len(line) + 1 > 3900:
                chunks.append(cur)
                cur = ""
            cur += line + "\n"
        chunks.append(cur)
        await interaction.response.send_message(
            embed=discord.Embed(title=title, color=BRAND, description=chunks[0]))
        for extra in chunks[1:]:
            await interaction.followup.send(embed=discord.Embed(color=BRAND, description=extra))

    @driver.command(name="profile", description="Show a driver's profile and penalty-point status.")
    @app_commands.describe(driver="Name, number or @mention of the driver")
    async def profile(self, interaction: discord.Interaction, driver: str):
        gid = interaction.guild_id
        d = database.find_driver(gid, driver)
        if not d:
            await interaction.response.send_message(
                f"Couldn't find a single driver matching `{driver}`. Try their car number or exact name.",
                ephemeral=True)
            return
        season = database.current_season(gid)
        pts = database.driver_points(gid, d["id"], d["division_id"], season)
        div = database.get_division(gid, d["division_id"]) if d["division_id"] else None
        embed = discord.Embed(title=f"Driver profile — {driver_label(d)}", color=BRAND)
        embed.add_field(name="Team", value=d["team"] or "—", inline=True)
        embed.add_field(name="Division", value=div["name"] if div else "—", inline=True)
        embed.add_field(name="Gamertag", value=d["gamertag"] or "—", inline=True)
        embed.add_field(name="Platform", value=d["platform"] or "—", inline=True)
        embed.add_field(name=f"Penalty points (S{season})", value=f"**{pts}**", inline=True)
        appeals = database.appeals_used(gid, d["id"], d["division_id"], season)
        embed.add_field(name="Appeals used", value=f"{appeals}/2", inline=True)
        await interaction.response.send_message(embed=embed)

    @driver.command(name="edit", description="Edit a driver's details.")
    @app_commands.describe(
        driver="Name, number or @mention of the driver to edit",
        name="New name", number="New car number", division="New division",
        team="New team", gamertag="New gamertag", platform="New platform",
    )
    @app_commands.autocomplete(division=division_autocomplete)
    @app_commands.choices(platform=PLATFORMS)
    async def edit(self, interaction: discord.Interaction, driver: str,
                   name: str = None, number: app_commands.Range[int, 0, 999] = None,
                   division: str = None, team: str = None, gamertag: str = None,
                   platform: app_commands.Choice[str] = None):
        gid = interaction.guild_id
        d = database.find_driver(gid, driver)
        if not d:
            await interaction.response.send_message(
                f"Couldn't find a single driver matching `{driver}`.", ephemeral=True)
            return
        division_id = int(division) if division and division.isdigit() else None
        database.update_driver(
            gid, d["id"], name=name, number=number, division_id=division_id,
            team=team, gamertag=gamertag,
            platform=platform.value if platform else None,
        )
        await interaction.response.send_message(
            f"Updated **{name or d['name']}**. Per rule 11D, moving a driver's division keeps their penalty points.",
            ephemeral=True)


async def setup(bot):
    await bot.add_cog(Drivers(bot))
