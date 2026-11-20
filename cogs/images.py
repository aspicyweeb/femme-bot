import discord
from discord import app_commands
from discord.ext import commands

NOTE = (
    "✅ **please copy the link below for use.**\n"
    "note: **do not** delete this message — the image link dies with it.\n\n"
    "{url}\n"
    "```\n{url}\n```"
)


class Images(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="imagelink", description="repost an image and get a cdn link that lasts")
    async def imagelink(self, interaction: discord.Interaction, image: discord.Attachment):
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message("Attach an image.", ephemeral=True)
            return
        # Interaction attachment URLs expire. Re-upload onto this message so the
        # link in the note is the one Discord will keep.
        if image.size > 8 * 1024 * 1024:
            await interaction.response.send_message("That image is over 8MB.", ephemeral=True)
            return
        try:
            file = await image.to_file()
        except Exception:
            await interaction.response.send_message("Couldn't read that image.", ephemeral=True)
            return
        await interaction.response.send_message(content="uploading…", file=file)
        msg = await interaction.original_response()
        if not msg.attachments:
            await msg.edit(content="Upload failed. Try again.")
            return
        await msg.edit(content=NOTE.format(url=msg.attachments[0].url))


async def setup(bot: commands.Bot):
    await bot.add_cog(Images(bot))
