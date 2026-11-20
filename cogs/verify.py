import logging

import discord
from discord import app_commands
from discord.ext import commands

import storage

log = logging.getLogger(__name__)


def _cfg(guild_id: int) -> dict:
    data = storage.load_obj("config.json")
    bucket = data.get(str(guild_id), {})
    return bucket if isinstance(bucket, dict) else {}


class Verify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _give(self, interaction: discord.Interaction, member: discord.Member, key: str, label: str) -> discord.Role | None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return None
        try:
            stored = _cfg(interaction.guild.id)
        except storage.DataError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return None
        role_id = stored.get("verify", {}).get(key) if isinstance(stored.get("verify"), dict) else None
        if not role_id:
            await interaction.response.send_message(f"Run /setverify and set the {label} role first.", ephemeral=True)
            return None
        try:
            role = interaction.guild.get_role(int(role_id))
        except (TypeError, ValueError):
            await interaction.response.send_message(f"The saved {label} role id is bad. Run /setverify again.", ephemeral=True)
            return None
        if role is None:
            await interaction.response.send_message(f"The {label} role was deleted. Run /setverify again.", ephemeral=True)
            return None
        me = interaction.guild.me
        if me is not None and role >= me.top_role:
            await interaction.response.send_message(
                f"Move my role above {role.mention} or I can't assign it.",
                ephemeral=True,
            )
            return None
        try:
            await member.add_roles(role, reason=f"{label} by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I can't assign {role.mention}. Move my role higher.",
                ephemeral=True,
            )
            return None
        return role

    @app_commands.command(name="verify18", description="Verify a member as 18+ and remove unverified")
    @app_commands.describe(member="Member to verify")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def verify18(self, interaction: discord.Interaction, member: discord.Member):
        role = await self._give(interaction, member, "18", "18+")
        if role is None:
            return
        note = ""
        try:
            stored = _cfg(interaction.guild.id)
        except storage.DataError as exc:
            await interaction.response.send_message(f"Gave {role.mention}, but couldn't read config: {exc}", ephemeral=True)
            return
        verify = stored.get("verify") if isinstance(stored.get("verify"), dict) else {}
        unverified_id = verify.get("unverified")
        if unverified_id:
            try:
                unverified = interaction.guild.get_role(int(unverified_id))
            except (TypeError, ValueError):
                unverified = None
            if unverified and unverified in member.roles:
                try:
                    await member.remove_roles(unverified, reason="removed unverified on 18+ verify")
                except discord.Forbidden:
                    note = " Couldn't remove the unverified role. Move my role higher."
        await interaction.response.send_message(f"Verified {member.mention} as 18+.{note}", ephemeral=True)

    @app_commands.command(name="verifycreator", description="Verify a member as creator")
    @app_commands.describe(member="Member to verify as creator")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def verifycreator(self, interaction: discord.Interaction, member: discord.Member):
        role = await self._give(interaction, member, "creator", "creator")
        if role is None:
            return
        await interaction.response.send_message(f"Gave {member.mention} the creator role.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        try:
            rid = _cfg(member.guild.id).get("autorole")
        except storage.DataError:
            log.exception("autorole: bad config")
            return
        if not rid:
            return
        try:
            role = member.guild.get_role(int(rid))
        except (TypeError, ValueError):
            log.warning("autorole: bad role id %s", rid)
            return
        if role is None:
            return
        try:
            await member.add_roles(role, reason="autorole")
        except discord.Forbidden:
            log.warning("autorole: can't assign %s. Move the bot role higher.", role.name)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verify(bot))
