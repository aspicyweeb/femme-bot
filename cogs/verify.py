import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def cfg(gid: int) -> dict:
    return load().get(str(gid), {})

class Verify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- Verify commands ----------------
    @app_commands.command(name="verify18", description="Verify a member as 18+ (removes unverified role)")
    @app_commands.describe(member="Member to verify")
    async def verify18(self, interaction: discord.Interaction, member: discord.Member):
        stored = cfg(interaction.guild_id)
        verify = stored.get("verify", {})
        role_id = verify.get("18")
        if not role_id:
            await interaction.response.send_message("Run `/setup` and set the 18+ role first.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message("The 18+ role was deleted. Run `/setup` again.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason=f"verify18 by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot can't assign the 18+ role.", ephemeral=True)
            return
        # Remove unverified role if set
        unverified_id = verify.get("unverified")
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
        verify = stored.get("verify", {})
        role_id = verify.get("creator")
        if not role_id:
            await interaction.response.send_message("Run `/setup` and set the creator role first.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message("The creator role was deleted. Run `/setup` again.", ephemeral=True)
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
