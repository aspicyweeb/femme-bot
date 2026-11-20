import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

import storage

log = logging.getLogger(__name__)


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def dest(self, guild, kind: str):
        if guild is None:
            return None
        try:
            data = storage.load_obj("config.json")
        except storage.DataError:
            log.exception("logs: bad config")
            return None
        cfg = data.get(str(guild.id), {})
        if not isinstance(cfg, dict):
            return None
        logs_cfg = cfg.get("logs")
        if not isinstance(logs_cfg, dict):
            return None
        cid = logs_cfg.get(kind)
        if not cid:
            return None
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            return None
        ch = guild.get_channel(cid) or guild.get_thread(cid)
        if isinstance(ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return ch
        return None

    async def send(self, guild, kind: str, title: str, body: str, color: int):
        ch = self.dest(guild, kind)
        if ch is None:
            return
        embed = discord.Embed(
            title=title,
            description=(body or "")[:4000],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            await ch.send(embed=embed)
        except discord.Forbidden:
            log.warning("logs: can't send in %s", getattr(ch, "name", ch.id))
        except discord.HTTPException:
            log.exception("logs: send failed")

    def _body(self, message: discord.Message) -> str:
        if message.content:
            return message.content
        if message.attachments:
            return "\n".join(a.url for a in message.attachments)
        return "*no text (maybe only an embed, or message content intent is off)*"

    async def _who_deleted(self, guild: discord.Guild, channel_id: int, author_id: int | None):
        me = guild.me
        if me is None or not me.guild_permissions.view_audit_log:
            return None
        await asyncio.sleep(1)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age > 20:
                    break
                extra_channel = getattr(entry.extra, "channel", None)
                if getattr(extra_channel, "id", None) != channel_id:
                    continue
                target_id = getattr(entry.target, "id", None)
                if author_id is not None and target_id != author_id:
                    continue
                return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        message = payload.cached_message
        if message is not None and getattr(message.author, "bot", False):
            return
        if message is not None:
            who = f"**{message.author}** (`{message.author.id}`)"
            where = getattr(message.channel, "mention", None) or f"<#{payload.channel_id}>"
            content = self._body(message)
            author_id = message.author.id
        else:
            who = "someone"
            ch = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
            where = ch.mention if ch is not None else f"<#{payload.channel_id}>"
            content = "*not in cache, so the text isn't available*"
            author_id = None
        deleter = await self._who_deleted(guild, payload.channel_id, author_id)
        by = f"\nDeleted by **{deleter}** (`{deleter.id}`)" if deleter else ""
        await self.send(
            guild,
            "messages",
            "Message deleted",
            f"{who} in {where}\n{content}{by}",
            0xFF6B6B,
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or after.author.bot:
            return
        if before.content == after.content:
            return
        await self.send(
            after.guild,
            "messages",
            "Message edited",
            f"**{after.author}** (`{after.author.id}`) in {after.channel.mention}\n"
            f"**Before:** {before.content or '*empty*'}\n"
            f"**After:** {after.content or '*empty*'}\n"
            f"[jump]({after.jump_url})",
            0xF4D35E,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        created = discord.utils.format_dt(member.created_at, "R")
        await self.send(
            member.guild,
            "members",
            "Member joined",
            f"{member.mention} **{member}** (`{member.id}`)\nAccount created {created}",
            0x7DDE92,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.send(
            member.guild,
            "members",
            "Member left",
            f"**{member}** (`{member.id}`)",
            0xFF9F1C,
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self.send(guild, "members", "Ban", f"**{user}** (`{user.id}`)", 0xD90429)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await self.send(guild, "members", "Unban", f"**{user}** (`{user.id}`)", 0x7DDE92)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        parts = []
        if before.nick != after.nick:
            parts.append(f"Nick: `{before.nick}` → `{after.nick}`")
        added = [r.mention for r in after.roles if r not in before.roles]
        removed = [r.mention for r in before.roles if r not in after.roles]
        if added:
            parts.append("Roles added: " + " ".join(added))
        if removed:
            parts.append("Roles removed: " + " ".join(removed))
        if before.timed_out_until != after.timed_out_until:
            parts.append(f"Timeout: `{before.timed_out_until}` → `{after.timed_out_until}`")
        if not parts:
            return
        await self.send(
            after.guild,
            "members",
            "Member updated",
            f"{after.mention} **{after}** (`{after.id}`)\n" + "\n".join(parts),
            0xC9A0FF,
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        mention = getattr(channel, "mention", None) or f"`{channel.name}`"
        await self.send(
            channel.guild,
            "random",
            "Channel created",
            f"{mention} `{channel.name}` ({channel.id})",
            0x7DDE92,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self.send(
            channel.guild,
            "random",
            "Channel deleted",
            f"`{channel.name}` ({channel.id})",
            0xFF6B6B,
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self.send(role.guild, "random", "Role created", f"{role.mention} `{role.name}`", 0x7DDE92)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self.send(role.guild, "random", "Role deleted", f"`{role.name}` (`{role.id}`)", 0xFF6B6B)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        parts = []
        if before.name != after.name:
            parts.append(f"Name: `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            parts.append("Icon changed")
        if not parts:
            return
        await self.send(after, "random", "Server updated", "\n".join(parts), 0xC9A0FF)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
