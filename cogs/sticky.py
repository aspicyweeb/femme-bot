import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import storage

log = logging.getLogger(__name__)
WHERE = discord.TextChannel | discord.Thread


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending: dict[int, asyncio.Task] = {}
        self.generation: dict[int, int] = {}

    def _bump(self, channel_id: int) -> int:
        gen = self.generation.get(channel_id, 0) + 1
        self.generation[channel_id] = gen
        old = self.pending.pop(channel_id, None)
        if old:
            old.cancel()
        return gen

    @app_commands.command(name="createsticky", description="post a plain message that stays at the bottom")
    @app_commands.describe(channel="channel to stick in", text="whatever you want. emotes allowed. not an embed.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def sticky_set(self, interaction: discord.Interaction, channel: WHERE, text: str):
        await interaction.response.defer(ephemeral=True)
        if not text.strip():
            await interaction.followup.send("Text is empty.", ephemeral=True)
            return
        if len(text) > 2000:
            await interaction.followup.send("Discord max is 2000 characters.", ephemeral=True)
            return
        self._bump(channel.id)
        try:
            async with storage.lock:
                data = storage.load_obj("stickies.json")
                previous = data.get(str(channel.id)) if isinstance(data.get(str(channel.id)), dict) else None
        except storage.DataError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        if previous and previous.get("message_id"):
            try:
                old = await channel.fetch_message(int(previous["message_id"]))
                await old.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
                pass
        try:
            msg = await channel.send(text)
        except discord.Forbidden:
            await interaction.followup.send("Bot can't send in that channel.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(f"Discord rejected that: {exc}", ephemeral=True)
            return
        try:
            async with storage.lock:
                data = storage.load_obj("stickies.json")
                data[str(channel.id)] = {"text": text, "message_id": msg.id}
                storage.save("stickies.json", data)
        except storage.DataError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(f"Sticky on in {channel.mention}", ephemeral=True)

    @app_commands.command(name="deletesticky", description="remove the sticky from a channel")
    @app_commands.describe(channel="channel to clear")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def sticky_off(self, interaction: discord.Interaction, channel: WHERE):
        await interaction.response.defer(ephemeral=True)
        self._bump(channel.id)
        try:
            async with storage.lock:
                data = storage.load_obj("stickies.json")
                entry = data.pop(str(channel.id), None)
                storage.save("stickies.json", data)
        except storage.DataError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        if isinstance(entry, dict) and entry.get("message_id"):
            try:
                old = await channel.fetch_message(int(entry["message_id"]))
                await old.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
                pass
        if not entry:
            await interaction.followup.send(f"No sticky was set in {channel.mention}", ephemeral=True)
            return
        await interaction.followup.send(f"Sticky off in {channel.mention}", ephemeral=True)

    async def refresh(self, channel: discord.abc.Messageable, gen: int):
        channel_id = channel.id
        try:
            await asyncio.sleep(2)
            if self.generation.get(channel_id) != gen:
                return
            async with storage.lock:
                data = storage.load_obj("stickies.json")
                entry = data.get(str(channel_id))
                if not isinstance(entry, dict) or not entry.get("text"):
                    return
                text = entry["text"]
                old_id = entry.get("message_id")
            if old_id:
                try:
                    old = await channel.fetch_message(int(old_id))
                    await old.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
                    pass
            if self.generation.get(channel_id) != gen:
                return
            new = await channel.send(text)
            if self.generation.get(channel_id) != gen:
                try:
                    await new.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return
            async with storage.lock:
                data = storage.load_obj("stickies.json")
                current = data.get(str(channel_id))
                if not isinstance(current, dict):
                    try:
                        await new.delete()
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    return
                current["message_id"] = new.id
                data[str(channel_id)] = current
                storage.save("stickies.json", data)
        except asyncio.CancelledError:
            return
        except storage.DataError:
            log.exception("sticky refresh failed")
        except discord.HTTPException:
            log.exception("sticky refresh rejected")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or self.bot.user is None:
            return
        try:
            data = storage.load_obj("stickies.json")
        except storage.DataError:
            log.exception("sticky: bad file")
            return
        entry = data.get(str(message.channel.id))
        if not isinstance(entry, dict):
            return
        if message.id == entry.get("message_id"):
            return
        # The sticky we just reposted matches this text. Anything else the bot
        # sends (like /say) should still push the sticky back to the bottom.
        if message.author.id == self.bot.user.id and message.content == entry.get("text"):
            return
        gen = self._bump(message.channel.id)
        self.pending[message.channel.id] = asyncio.create_task(self.refresh(message.channel, gen))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
