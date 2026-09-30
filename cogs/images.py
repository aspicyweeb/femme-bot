import discord
from discord import app_commands
from discord.ext import commands

NOTE = (
    "✅ **please copy the link below for use.**\n"
    "note: **do not** delete this message or channel - the image link may no longer be valid if you do so.\n\n"
    "{url}\n"
    "```\n{url}\n```"
)


class Images(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="imagelink", description="get a copy-paste discord cdn link for an image")
    async def imagelink(self, interaction: discord.Interaction, image: discord.Attachment):
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message("Attach an image.", ephemeral=True)
            return
        await interaction.response.send_message(NOTE.format(url=image.url))


async def setup(bot: commands.Bot):
    await bot.add_cog(Images(bot))
