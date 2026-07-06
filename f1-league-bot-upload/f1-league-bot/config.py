"""Loads settings from the .env file so the rest of the bot can use them."""
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

_guild = os.getenv("GUILD_ID")
GUILD_ID = int(_guild) if _guild and _guild.strip().isdigit() else None

# Where the league data is stored (a single file — easy to back up).
DB_PATH = os.getenv("DB_PATH", "data/league.db")

# A friendly check so beginners get a clear error instead of a cryptic one.
if not DISCORD_TOKEN or DISCORD_TOKEN == "paste-your-bot-token-here":
    raise SystemExit(
        "\n[!] No Discord token found.\n"
        "    1. Copy the file '.env.example' to '.env'\n"
        "    2. Open '.env' and paste your bot token after DISCORD_TOKEN=\n"
        "    See the README for step-by-step help.\n"
    )
