"""F1 League Bot — main entry point.

Run it with:   python bot.py

It loads the command groups from the 'cogs' folder, connects to Discord, and
registers the slash commands so they appear in your server.
"""
import asyncio
import logging

import discord
from discord.ext import commands

import config
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("f1bot")

# Slash commands don't need the privileged "message content" intent, so the
# default intents are all we need. This keeps setup simple for beginners.
intents = discord.Intents.default()

COGS = [
    "cogs.setup",
    "cogs.drivers",
    "cogs.incidents",
    "cogs.steward",
]


class F1Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        database.init_db()
        for ext in COGS:
            await self.load_extension(ext)
            log.info("Loaded %s", ext)

        # Sync commands. If GUILD_ID is set, sync to that one server so the
        # commands show up INSTANTLY (global sync can take up to an hour).
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to guild %s", len(synced), config.GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands (may take up to 1 hour to appear)", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (id: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="the championship")
        )


async def main():
    bot = F1Bot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped.")
