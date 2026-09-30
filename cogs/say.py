import discord
from discord import app_commands
from discord.ext import commands


class Say(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="Post a plain message as the bot")
    @app_commands.describe(
        text="What the bot should say. Emotes allowed.",
        channel="Defaults to this channel",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def say(
        self,
        interaction: discord.Interaction,
        text: str,
        channel: discord.TextChannel | None = None,
    ):
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        if len(text) > 2000:
            await interaction.response.send_message("Max 2000 characters.", ephemeral=True)
            return
        try:
            await channel.send(text)
        except discord.Forbidden:
            await interaction.response.send_message("Bot can't send there.", ephemeral=True)
            return
        await interaction.response.send_message("Posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Say(bot))
