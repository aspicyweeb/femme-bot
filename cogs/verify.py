import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "verify.json"


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def cfg(gid: int) -> dict:
    return load().get(str(gid), {})


class Verify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- Autorole ----------------
    @app_commands.command(name="autoroleset", description="role given to everyone who joins")
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild.me.top_role <= role:
            await interaction.response.send_message("Move the bot role above that role.", ephemeral=True)
            return
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry["autorole"] = role.id
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message(f"Join role → {role.mention}", ephemeral=True)

    @app_commands.command(name="autoroleoff", description="stop giving a role on join")
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_off(self, interaction: discord.Interaction):
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry.pop("autorole", None)
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message("Autorole off.", ephemeral=True)

    # ---------------- Unverified role ----------------
    @app_commands.command(name="unverifiedset", description="role removed when someone is verified as 18+")
    @app_commands.checks.has_permissions(administrator=True)
    async def unverifiedset(self, interaction: discord.Interaction, role: discord.Role):
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry["unverified"] = role.id
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message(f"Will remove {role.mention} on /verify18", ephemeral=True)

    # ---------------- Setup ----------------
    @app_commands.command(name="verify18setup", description="Set the 18+ role")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify18_setup(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild.me.top_role <= role:
            await interaction.response.send_message("Move the bot role above that role.", ephemeral=True)
            return
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry["role_18"] = role.id
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message(f"18+ role set to {role.mention}", ephemeral=True)

    @app_commands.command(name="verifycreatorsetup", description="Set the creator role")
    @app_commands.checks.has_permissions(administrator=True)
    async def verifycreator_setup(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild.me.top_role <= role:
            await interaction.response.send_message("Move the bot role above that role.", ephemeral=True)
            return
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry["role_creator"] = role.id
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message(f"Creator role set to {role.mention}", ephemeral=True)

    # ---------------- Verify commands ----------------
    @app_commands.command(name="verify18", description="Verify a member as 18+ (removes unverified role)")
    @app_commands.describe(member="Member to verify")
    async def verify18(self, interaction: discord.Interaction, member: discord.Member):
        stored = cfg(interaction.guild_id)
        role_id = stored.get("role_18")
        if not role_id:
            await interaction.response.send_message("Run `/verify18setup` first.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message("The 18+ role was deleted. Run setup again.", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason=f"verify18 by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot can't assign the 18+ role.", ephemeral=True)
            return

        # Remove unverified role if set
        unverified_id = stored.get("unverified")
        if unverified_id:
            unverified = interaction.guild.get_role(int(unverified_id))
            if unverified and unverified in member.roles:
                try:
                    await member.remove_roles(unverified, reason="removed unverified on 18+ verify")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"Verified {member.mention} as 18+ but couldn't remove the unverified role. Move the bot role higher.",
                        ephemeral=True,
                    )
                    return

        await interaction.response.send_message(f"Verified {member.mention} as 18+.", ephemeral=True)

    @app_commands.command(name="verifycreator", description="Verify a member as creator")
    @app_commands.describe(member="Member to verify as creator")
    async def verifycreator(self, interaction: discord.Interaction, member: discord.Member):
        stored = cfg(interaction.guild_id)
        role_id = stored.get("role_creator")
        if not role_id:
            await interaction.response.send_message("Run `/verifycreatorsetup` first.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message("The creator role was deleted. Run setup again.", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason=f"verifycreator by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot can't assign the creator role.", ephemeral=True)
            return

        await interaction.response.send_message(f"Gave {member.mention} the creator role.", ephemeral=True)

    # ---------------- Autorole on join ----------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        rid = cfg(member.guild.id).get("autorole")
        if not rid:
            return
        role = member.guild.get_role(int(rid))
        if role is None:
            return
        try:
            await member.add_roles(role, reason="autorole")
        except discord.Forbidden:
            print("autorole: missing perms")


async def setup(bot: commands.Bot):
    await bot.add_cog(Verify(bot))
