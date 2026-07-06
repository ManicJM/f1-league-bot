"""Shared helpers used across the command modules."""
import discord

import database

# League brand colour for embeds
BRAND = discord.Color.from_rgb(225, 6, 0)   # F1 red


def resolve_division(interaction):
    """Figure out which division a command is acting on.

    Priority:
      1) the channel the command was used in (if it's a division's reports channel)
      2) the division of the command user's registered driver profile
    Returns a division row, or None if it can't be determined.
    """
    gid = interaction.guild_id
    div = database.division_for_channel(gid, interaction.channel_id)
    if div:
        return div
    driver = database.find_driver(gid, str(interaction.user.id))
    if driver and driver["division_id"]:
        return database.get_division(gid, driver["division_id"])
    return None


def is_steward_for(interaction, division):
    """True if the user may act as a steward for this division:
    they have the division's steward role, or they have manage-guild permission."""
    if interaction.user.guild_permissions.manage_guild:
        return True
    if division and division["steward_role_id"]:
        role_ids = {str(r.id) for r in getattr(interaction.user, "roles", [])}
        return str(division["steward_role_id"]) in role_ids
    return False


def driver_label(driver):
    if not driver:
        return "Unknown driver"
    num = f"#{driver['number']} " if driver["number"] is not None else ""
    mention = f" (<@{driver['user_id']}>)" if driver["user_id"] else ""
    return f"{num}{driver['name']}{mention}"


def _row_get(row, key):
    """Safely read a column that may not exist on older rows."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def render_case_embed(guild_id, incident):
    """Build the single consolidated 'case card': report + every defence +
    the final decision, all in one embed. Used for the organised-channel card
    and for /incident view so both always look identical."""
    accused = database.get_driver(guild_id, incident["accused_driver_id"]) if incident["accused_driver_id"] else None
    defences = database.get_defences(incident["id"])
    verdict = database.get_verdict_for_incident(guild_id, incident["id"])
    closed = incident["status"] == "closed" or verdict is not None

    color = discord.Color.green() if verdict else discord.Color.orange()
    status = "⚫ Closed" if closed else "🟠 Open — awaiting steward decision"
    embed = discord.Embed(
        title=f"Case #{incident['case_number']} — {status}",
        color=color,
        description=incident["description"] or "—",
    )
    embed.add_field(name="Reported by",
                    value=f"<@{incident['reporter_id']}>" if incident["reporter_id"] else "—", inline=True)
    embed.add_field(name="Accused", value=driver_label(accused), inline=True)
    embed.add_field(name="Lap / Corner",
                    value=f"{incident['lap']} / {incident['corner'] or '—'}", inline=True)
    if incident["footage_url"]:
        embed.add_field(name="📹 Report footage", value=incident["footage_url"], inline=False)

    if defences:
        for d in defences:
            val = d["description"] or "—"
            if d["footage_url"]:
                val += f"\n📹 Footage: {d['footage_url']}"
            who = f"<@{d['submitter_id']}>" if d["submitter_id"] else "driver"
            embed.add_field(name=f"🔵 Defence by {who}", value=val, inline=False)
    else:
        embed.add_field(name="🔵 Defence", value="_none submitted yet_", inline=False)

    if verdict:
        pen = format_penalty(verdict["seconds"], verdict["points"], verdict["ban"])
        decision = f"**{verdict['rule_code'] or '—'}** — {pen}"
        if verdict["notes"]:
            decision += f"\n_{verdict['notes']}_"
        embed.add_field(name="⚖️ Decision", value=decision, inline=False)

    embed.set_footer(text=f"Case #{incident['case_number']} • season {incident['season']}")
    return embed


async def update_organised_card(guild, guild_id, division, incident):
    """Create or edit the single consolidated case card in the division's
    organised (stewards) channel. Returns the channel it lives in, or None."""
    if not (division and division["organised_channel_id"]):
        return None
    org = guild.get_channel(int(division["organised_channel_id"]))
    if org is None:
        return None

    embed = render_case_embed(guild_id, incident)
    msg_id = _row_get(incident, "organised_message_id")
    if msg_id:
        try:
            msg = await org.fetch_message(int(msg_id))
            await msg.edit(embed=embed)
            return org
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass  # message deleted or unreachable — fall through and repost

    msg = await org.send(
        content=f"🗂️ **Case #{incident['case_number']}** — report & defences together (updates as new info arrives).",
        embed=embed,
    )
    database.set_incident_organised_message(incident["id"], org.id, msg.id)
    return org


def format_penalty(seconds, points, ban):
    parts = []
    if seconds:
        parts.append(f"**{seconds}s** time penalty")
    if points:
        parts.append(f"**{points}** penalty point{'s' if points != 1 else ''}")
    if ban:
        parts.append(f"**{ban.capitalize()} ban**")
    return ", ".join(parts) if parts else "No further action"
