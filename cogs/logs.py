import json
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "logs.json"


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def dest(self, guild, kind: str):
        if guild is None:
            return None
        data = load()
        cfg = data.get(str(guild.id), {})
        cid = cfg.get(kind)
        if not cid:
            return None
        ch = guild.get_channel(int(cid))
        return ch if isinstance(ch, discord.TextChannel) else None

    async def send(self, guild, kind: str, title: str, body: str, color: int):
        ch = self.dest(guild, kind)
        if ch is None:
            return
        embed = discord.Embed(
            title=title,
            description=body[:4000],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            await ch.send(embed=embed)
        except discord.Forbidden:
            print("logs: missing send perms")

    @app_commands.command(name="logsmessages", description="Channel for deleted/edited messages")
    @app_commands.describe(channel="Where message logs go")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_messages(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load()
        cfg = data.get(str(interaction.guild_id), {})
        cfg["messages"] = channel.id
        data[str(interaction.guild_id)] = cfg
        save(data)
        await interaction.response.send_message(f"Message logs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="logsmembers", description="Channel for joins, leaves, roles, bans")
    @app_commands.describe(channel="Where member logs go")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_members(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load()
        cfg = data.get(str(interaction.guild_id), {})
        cfg["members"] = channel.id
        data[str(interaction.guild_id)] = cfg
        save(data)
        await interaction.response.send_message(f"Member logs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="logsrandom", description="Channel for server/channel/role changes")
    @app_commands.describe(channel="Where extra logs go")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_random(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load()
        cfg = data.get(str(interaction.guild_id), {})
        cfg["random"] = channel.id
        data[str(interaction.guild_id)] = cfg
        save(data)
        await interaction.response.send_message(f"Random logs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="logsoff", description="Stop all logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_off(self, interaction: discord.Interaction):
        data = load()
        data.pop(str(interaction.guild_id), None)
        save(data)
        await interaction.response.send_message("Logs off", ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        content = message.content or "*no text (maybe only an image)*"
        await self.send(
            message.guild,
            "messages",
            "Message deleted",
            f"**{message.author}** (`{message.author.id}`) in {message.channel.mention}\n{content}",
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
        await self.send(
            channel.guild,
            "random",
            "Channel created",
            f"{channel.mention} `{channel.name}` ({channel.id})",
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

