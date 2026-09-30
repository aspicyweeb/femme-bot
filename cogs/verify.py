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

    @app_commands.command(name="autorole_set", description="Role given to everyone who joins")
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

    @app_commands.command(name="autorole_off", description="Stop giving a role on join")
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_off(self, interaction: discord.Interaction):
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry.pop("autorole", None)
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message("Autorole off.", ephemeral=True)

    @app_commands.command(name="verify_domme", description="Give a member any roles you list")
    @app_commands.describe(member="Who you're verifying", roles="Mention every role: @verified @domme @whatever")
    async def verify_domme(self, interaction: discord.Interaction, member: discord.Member, roles: str):
        await self.give(interaction, member, roles, "domme")

    @app_commands.command(name="verify_sub", description="Give a member any roles you list")
    @app_commands.describe(member="Who you're verifying", roles="Mention every role: @verified @sub @whatever")
    async def verify_sub(self, interaction: discord.Interaction, member: discord.Member, roles: str):
        await self.give(interaction, member, roles, "sub")

    async def give(self, interaction: discord.Interaction, member: discord.Member, roles_str: str, key: str):
        found = []
        for mention in roles_str.split():
            if mention.startswith("<@&") and mention.endswith(">"):
                rid = mention[3:-1]
                if rid.isdigit():
                    role = interaction.guild.get_role(int(rid))
                    if role:
                        found.append(role)
        if not found:
            await interaction.response.send_message("Mention the roles in the roles field.", ephemeral=True)
            return
        too_high = [r.name for r in found if interaction.guild.me.top_role <= r]
        if too_high:
            await interaction.response.send_message("Move the bot role above: " + ", ".join(too_high), ephemeral=True)
            return
        try:
            await member.add_roles(*found, reason=f"verify_{key} by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot can't assign those roles.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Verified {member.mention} → " + " ".join(r.mention for r in found),
            ephemeral=True,
        )

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
