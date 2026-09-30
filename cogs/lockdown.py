import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "hidden.json"


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def everyone(guild: discord.Guild) -> discord.Role:
    return guild.default_role


def dump_overwrites(channel: discord.abc.GuildChannel) -> list:
    rows = []
    for target, ow in channel.overwrites.items():
        allow, deny = ow.pair()
        kind = "role" if isinstance(target, discord.Role) else "member"
        rows.append({"kind": kind, "id": target.id, "allow": allow.value, "deny": deny.value})
    return rows


class Lockdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hide", description="Hide from members except Administrator. Remembers old perms.")
    @app_commands.describe(channel="Defaults to this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def hide(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Pick a text channel.", ephemeral=True)
            return
        guild = interaction.guild
        data = load()
        data[str(channel.id)] = dump_overwrites(channel)
        save(data)
        try:
            await channel.set_permissions(guild.me, view_channel=True, send_messages=True, reason="hide: keep bot")
            for role in guild.roles:
                if role.is_default() or not role.permissions.administrator:
                    await channel.set_permissions(role, view_channel=False, reason=f"hide by {interaction.user}")
                else:
                    await channel.set_permissions(role, view_channel=True, reason=f"hide by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("Bot needs Manage Channel and a role above the ones it edits.", ephemeral=True)
            return
        await interaction.followup.send(f"Hidden {channel.mention}. /unhide will restore the old permissions.", ephemeral=True)

    @app_commands.command(name="unhide", description="Restore the permissions from before /hide")
    @app_commands.describe(channel="Defaults to this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def unhide(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Pick a text channel.", ephemeral=True)
            return
        data = load()
        saved = data.get(str(channel.id))
        if not saved:
            await interaction.followup.send(
                "No saved permissions for this channel. Won't unhide — that would open it to unverified. Hide it with /hide first next time.",
                ephemeral=True,
            )
            return
        try:
            await channel.edit(overwrites={}, reason=f"unhide reset by {interaction.user}")
            for row in saved:
                target = (
                    interaction.guild.get_role(row["id"])
                    if row["kind"] == "role"
                    else interaction.guild.get_member(row["id"])
                )
                if target is None:
                    continue
                ow = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(row["allow"]),
                    discord.Permissions(row["deny"]),
                )
                await channel.set_permissions(target, overwrite=ow, reason=f"unhide by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("Bot needs Manage Channel here.", ephemeral=True)
            return
        data.pop(str(channel.id), None)
        save(data)
        await interaction.followup.send(f"Restored old permissions on {channel.mention}", ephemeral=True)

    @app_commands.command(name="lock", description="No one can talk. Channel stays visible.")
    @app_commands.describe(
        channel="Defaults to this channel",
        message="Public text the bot posts. Leave blank for the default.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
    ):
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        try:
            await channel.set_permissions(
                interaction.guild.me,
                send_messages=True,
                view_channel=True,
                reason="lock: bot can still speak",
            )
            await channel.set_permissions(
                everyone(interaction.guild),
                send_messages=False,
                reason=f"lock by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message("Bot needs Manage Channel here.", ephemeral=True)
            return
        text = message or "🔒 this channel is locked. don't spam staff — wait."
        try:
            await channel.send(text)
        except discord.Forbidden:
            await interaction.response.send_message("Locked, but the bot couldn't post the notice.", ephemeral=True)
            return
        await interaction.response.send_message(f"Locked {channel.mention}", ephemeral=True)

    @app_commands.command(name="unlock", description="Allow talking again")
    @app_commands.describe(
        channel="Defaults to this channel",
        message="Optional public text when unlocking",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
    ):
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        try:
            await channel.set_permissions(
                everyone(interaction.guild),
                send_messages=None,
                reason=f"unlock by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message("Bot needs Manage Channel here.", ephemeral=True)
            return
        notice = message or "🔓 unlocked."
        try:
            await channel.send(notice)
        except discord.Forbidden:
            pass
        await interaction.response.send_message(f"Unlocked {channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lockdown(bot))
