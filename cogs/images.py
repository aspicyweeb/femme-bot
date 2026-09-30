import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "images.json"
DUMP_FILE = Path(__file__).resolve().parent.parent / "data" / "linkdump.json"

NOTE = (
    "✅ please copy the link below for use.\n"
    "note: do not delete this message or channel - the image link may no longer be valid if you do so.\n\n"
    "{url}\n\n"
    "{url}"
)


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_dump() -> dict:
    DUMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DUMP_FILE.exists():
        return json.loads(DUMP_FILE.read_text(encoding="utf-8"))
    return {}


def save_dump(data: dict) -> None:
    DUMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    DUMP_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def key_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


class Images(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def store(self, guild_id: int) -> dict:
        return load().get(str(guild_id), {})

    @app_commands.command(name="image_add", description="Save an image link under a name")
    @app_commands.describe(name="What people type, like rules or menu", url="Direct image link (png/jpg/gif/webp)")
    @app_commands.checks.has_permissions(administrator=True)
    async def image_add(self, interaction: discord.Interaction, name: str, url: str):
        name = key_name(name)
        if not name or len(name) > 32:
            await interaction.response.send_message("Name must be 1–32 characters.", ephemeral=True)
            return
        data = load()
        guild = data.get(str(interaction.guild_id), {})
        guild[name] = url.strip()
        data[str(interaction.guild_id)] = guild
        save(data)
        await interaction.response.send_message(f"Saved `{name}`. Use `/image {name}` or type `{name}` alone in chat.", ephemeral=True)

    @app_commands.command(name="image_delete", description="Remove a saved image")
    @app_commands.checks.has_permissions(administrator=True)
    async def image_delete(self, interaction: discord.Interaction, name: str):
        name = key_name(name)
        data = load()
        guild = data.get(str(interaction.guild_id), {})
        if name not in guild:
            await interaction.response.send_message("Not saved.", ephemeral=True)
            return
        guild.pop(name)
        data[str(interaction.guild_id)] = guild
        save(data)
        await interaction.response.send_message(f"Deleted `{name}`.", ephemeral=True)

    @app_commands.command(name="image_list", description="List saved image names")
    async def image_list(self, interaction: discord.Interaction):
        guild = self.store(interaction.guild_id)
        if not guild:
            await interaction.response.send_message("None saved.", ephemeral=True)
            return
        names = ", ".join(f"`{n}`" for n in sorted(guild))
        await interaction.response.send_message(names[:1900], ephemeral=True)

    @app_commands.command(name="image", description="Post a saved image")
    async def image(self, interaction: discord.Interaction, name: str):
        url = self.store(interaction.guild_id).get(key_name(name))
        if not url:
            await interaction.response.send_message("Unknown name. `/image_list`", ephemeral=True)
            return
        await interaction.response.send_message(url)

    @app_commands.command(name="linkdump_set", description="Channel where dropped images get copy-paste CDN links")
    @app_commands.checks.has_permissions(administrator=True)
    async def linkdump_set(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data = load_dump()
        data[str(interaction.guild_id)] = channel.id
        save_dump(data)
        await interaction.response.send_message(f"Drop images in {channel.mention}. Bot will reply with the link.", ephemeral=True)

    @app_commands.command(name="linkdump", description="Post copy-paste links for an image")
    async def linkdump(self, interaction: discord.Interaction, image: discord.Attachment):
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message("Attach an image.", ephemeral=True)
            return
        await interaction.response.send_message(NOTE.format(url=image.url))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        dump_id = load_dump().get(str(message.guild.id))
        if dump_id and message.channel.id == int(dump_id) and message.attachments:
            for att in message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    try:
                        await message.channel.send(NOTE.format(url=att.url))
                    except discord.Forbidden:
                        return
            return
        name = key_name(message.content)
        if not name:
            return
        url = self.store(message.guild.id).get(name)
        if not url:
            return
        try:
            await message.channel.send(url)
        except discord.Forbidden:
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Images(bot))
