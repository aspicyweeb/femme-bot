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

    @app_commands.command(name="verify_dom_setup", description="Two roles /verify_dom will give")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_dom_setup(self, interaction: discord.Interaction, role1: discord.Role, role2: discord.Role):
        await self.save_pair(interaction, "dom", role1, role2)

    @app_commands.command(name="verify_sub_setup", description="Two roles /verify_sub will give")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_sub_setup(self, interaction: discord.Interaction, role1: discord.Role, role2: discord.Role):
        await self.save_pair(interaction, "sub", role1, role2)

    async def save_pair(self, interaction, key: str, role1: discord.Role, role2: discord.Role):
        for r in (role1, role2):
            if interaction.guild.me.top_role <= r:
                await interaction.response.send_message(f"Move the bot role above **{r.name}**.", ephemeral=True)
                return
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry[key] = [role1.id, role2.id]
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message(
            f"`/{'verify_dom' if key == 'dom' else 'verify_sub'}` will give {role1.mention} + {role2.mention}",
            ephemeral=True,
        )

    @app_commands.command(name="verify_dom", description="Get the Dom verified roles")
    async def verify_dom(self, interaction: discord.Interaction):
        await self.give(interaction, "dom")

    @app_commands.command(name="verify_sub", description="Get the Sub verified roles")
    async def verify_sub(self, interaction: discord.Interaction):
        await self.give(interaction, "sub")

    async def give(self, interaction: discord.Interaction, key: str):
        ids = cfg(interaction.guild_id).get(key)
        if not ids:
            await interaction.response.send_message("Not set up. An admin needs to run the setup command first.", ephemeral=True)
            return
        roles = [interaction.guild.get_role(i) for i in ids]
        roles = [r for r in roles if r]
        if len(roles) != 2:
            await interaction.response.send_message("A setup role was deleted. Run setup again.", ephemeral=True)
            return
        try:
            await interaction.user.add_roles(*roles, reason=f"verify_{key}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot can't assign those roles.", ephemeral=True)
            return
        await interaction.response.send_message("Roles given: " + " ".join(r.mention for r in roles), ephemeral=True)

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
