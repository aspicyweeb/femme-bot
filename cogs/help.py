import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="commands", description="list every command this bot has right now")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def commands_list(self, interaction: discord.Interaction):
        lines = []
        for cmd in sorted(self.bot.tree.get_commands(), key=lambda c: c.name):
            if isinstance(cmd, app_commands.Group):
                for sub in cmd.commands:
                    lines.append(f"/{cmd.name} {sub.name} — {sub.description}")
            else:
                lines.append(f"/{cmd.name} — {cmd.description}")
        if not lines:
            await interaction.response.send_message("No slash commands loaded.", ephemeral=True)
            return
        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1900] + "\n…"
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
