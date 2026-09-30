import asyncio
import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "stickies.json"


def load_stickies() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save_stickies(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending: dict[int, asyncio.Task] = {}

    @app_commands.command(name="create_sticky", description="Post a plain message that stays at the bottom")
    @app_commands.describe(channel="Channel to stick in", text="Whatever you want. Emotes allowed. Not an embed.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_set(self, interaction: discord.Interaction, channel: discord.TextChannel, text: str):
        await interaction.response.defer(ephemeral=True)
        if len(text) > 2000:
            await interaction.followup.send("Discord max is 2000 characters.", ephemeral=True)
            return
        try:
            msg = await channel.send(text)
        except discord.Forbidden:
            await interaction.followup.send("Bot can't send in that channel.", ephemeral=True)
            return
        data = load_stickies()
        data[str(channel.id)] = {"text": text, "message_id": msg.id}
        save_stickies(data)
        await interaction.followup.send(f"Sticky on in {channel.mention}", ephemeral=True)

    @app_commands.command(name="delete_sticky", description="Remove the sticky from a channel")
    @app_commands.describe(channel="Channel to clear")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_off(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load_stickies()
        data.pop(str(channel.id), None)
        save_stickies(data)
        task = self.pending.pop(channel.id, None)
        if task:
            task.cancel()
        await interaction.response.send_message(f"Sticky off in {channel.mention}", ephemeral=True)

    async def refresh(self, channel: discord.TextChannel):
        await asyncio.sleep(2)
        data = load_stickies()
        entry = data.get(str(channel.id))
        if not entry:
            return
        old_id = entry.get("message_id")
        if old_id:
            try:
                old = await channel.fetch_message(old_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        try:
            new = await channel.send(entry["text"])
        except discord.Forbidden:
            return
        entry["message_id"] = new.id
        data[str(channel.id)] = entry
        save_stickies(data)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        entry = load_stickies().get(str(message.channel.id))
        if not entry:
            return
        if message.id == entry.get("message_id"):
            return
        old = self.pending.get(message.channel.id)
        if old:
            old.cancel()
        self.pending[message.channel.id] = asyncio.create_task(self.refresh(message.channel))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
