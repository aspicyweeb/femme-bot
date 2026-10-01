import discord
from discord import app_commands
from discord.ext import commands


class Say(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="post a message as the bot. images optional.")
    @app_commands.describe(
        text="what the bot should say. can leave empty if you only attach images.",
        channel="defaults to this channel",
        image="first image or file",
        image2="second image or file",
        image3="third image or file",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def say(
        self,
        interaction: discord.Interaction,
        text: str | None = None,
        channel: discord.TextChannel | None = None,
        image: discord.Attachment | None = None,
        image2: discord.Attachment | None = None,
        image3: discord.Attachment | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("pick a text channel.", ephemeral=True)
            return
        content = (text or "").strip()
        files = []
        for att in (image, image2, image3):
            if att is None:
                continue
            try:
                files.append(await att.to_file())
            except Exception:
                await interaction.followup.send("couldn't read an attachment.", ephemeral=True)
                return
        if not content and not files:
            await interaction.followup.send("type text or attach an image.", ephemeral=True)
            return
        if len(content) > 2000:
            await interaction.followup.send("max 2000 characters.", ephemeral=True)
            return
        try:
            await channel.send(content or None, files=files)
        except discord.Forbidden:
            await interaction.followup.send("bot can't send there.", ephemeral=True)
            return
        await interaction.followup.send("posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Say(bot))
