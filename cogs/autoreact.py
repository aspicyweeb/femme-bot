import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "autoreact.json"


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def react_token(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">") and ":" in raw:
        parts = raw.strip("<>").split(":")
        if len(parts) >= 3 and parts[-1].isdigit():
            return parts[-1]
    return raw


class AutoReact(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="autoreactsetup", description="bot reacts to every message in a channel")
    @app_commands.describe(
        channel="channel to watch",
        emotes="emotes in order, separated by spaces. custom server emotes work.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autoreactsetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        emotes: str,
    ):
        tokens = [react_token(e) for e in emotes.split() if e.strip()]
        if not tokens:
            await interaction.response.send_message("list at least one emote.", ephemeral=True)
            return
        if len(tokens) > 20:
            await interaction.response.send_message("discord max is 20 reactions.", ephemeral=True)
            return
        data = load()
        guild = data.get(str(interaction.guild_id), {})
        guild[str(channel.id)] = tokens
        data[str(interaction.guild_id)] = guild
        save(data)
        await interaction.response.send_message(
            f"auto react on in {channel.mention} ({len(tokens)} emotes).",
            ephemeral=True,
        )

    @app_commands.command(name="autoreactoff", description="stop auto reacting in a channel")
    @app_commands.describe(channel="channel to stop")
    @app_commands.checks.has_permissions(administrator=True)
    async def autoreactoff(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load()
        guild = data.get(str(interaction.guild_id), {})
        guild.pop(str(channel.id), None)
        data[str(interaction.guild_id)] = guild
        save(data)
        await interaction.response.send_message(f"auto react off in {channel.mention}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        tokens = load().get(str(message.guild.id), {}).get(str(message.channel.id))
        if not tokens:
            return
        for token in tokens:
            try:
                await message.add_reaction(token)
            except discord.HTTPException:
                continue


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReact(bot))
