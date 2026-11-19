import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path("/data/config.json")
COLOR = 0xC9A0FF

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_welcome(guild_id: int) -> dict:
    return load().get(str(guild_id), {}).get("welcome", {})

def fill(text: str, member: discord.Member) -> str:
    return (
        text.replace("{user}", member.mention)
        .replace("{name}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or ""))
    )

class WelcomeModal(discord.ui.Modal, title="Welcome Setup"):
    channel = discord.ui.TextInput(
        label="Welcome channel",
        placeholder="#general or channel ID",
        required=True,
    )
    line = discord.ui.TextInput(label="Line", default="hi there {user}! 💎", required=False)
    title = discord.ui.TextInput(label="Title", default="welcome to {server}", required=False)
    body = discord.ui.TextInput(
        label="Body",
        style=discord.TextStyle.paragraph,
        default="you made it.",
        required=False,
    )
    image = discord.ui.TextInput(label="Thumbnail URL (optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.channel.value.strip()

        # Handle <#123> or plain ID
        if raw.startswith("<#") and raw.endswith(">"):
            channel_id_str = raw[2:-1]
        else:
            channel_id_str = raw

        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return await interaction.response.send_message(
                "Use a channel mention (#channel) or the channel ID.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "That channel is invalid or not a text channel.",
                ephemeral=True,
            )

        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        welcome = data[guild].setdefault("welcome", {})
        welcome["channel_id"] = channel_id
        welcome["line"] = self.line.value.strip() or "hi there {user}! 💎"
        welcome["title"] = self.title.value.strip() or "welcome to {server}"
        welcome["body"] = self.body.value.strip() or "you made it."
        if self.image.value.strip():
            welcome["image"] = self.image.value.strip()
        else:
            welcome.pop("image", None)
        save(data)

        await interaction.response.send_message(
            f"Welcome set for {channel.mention}. Use `/welcometest` to preview.",
            ephemeral=True,
        )

class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build(self, member: discord.Member, data: dict) -> tuple[str, discord.Embed]:
        line = fill(data.get("line") or "hi there {user}!", member)
        embed = discord.Embed(
            title=fill(data.get("title") or f"welcome to {member.guild.name}", member),
            description=fill(data.get("body") or "you made it.", member),
            color=COLOR,
        )
        thumb = (data.get("image") or "").strip()
        if thumb:
            embed.set_thumbnail(url=thumb)
        return line, embed

    async def send_welcome(self, member: discord.Member) -> str | None:
        data = get_welcome(member.guild.id)
        if not data.get("channel_id"):
            return "Welcome not set up. Use /welcomesetup."
        channel = member.guild.get_channel(int(data["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return "Welcome channel is gone."
        line, embed = self.build(member, data)
        try:
            await channel.send(line, embed=embed)
        except discord.Forbidden:
            return "Bot can't send in that channel."
        return None

    @app_commands.command(name="welcomesetup", description="Set up welcome messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomesetup(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WelcomeModal())

    @app_commands.command(name="welcometest", description="Send a welcome preview")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcometest(self, interaction: discord.Interaction, member: discord.Member | None = None):
        err = await self.send_welcome(member or interaction.user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await interaction.response.send_message("Sent preview.", ephemeral=True)

    @app_commands.command(name="welcomeoff", description="Turn off welcome messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomeoff(self, interaction: discord.Interaction):
        data = load()
        guild = str(interaction.guild_id)
        if guild in data:
            data[guild].pop("welcome", None)
            save(data)
        await interaction.response.send_message("Welcome turned off.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self.send_welcome(member)

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))