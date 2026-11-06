import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"
COLOR = 0xC9A0FF

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def cfg(gid: int) -> dict:
    return load().get(str(gid), {}).get("welcome", {})

def fill(text: str, member: discord.Member) -> str:
    return (
        text.replace("{user}", member.mention)
        .replace("{name}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or ""))
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
        banner = (data.get("banner") or "").strip()
        if banner:
            embed.set_image(url=banner)
        return line, embed

    async def send_welcome(self, member: discord.Member) -> str | None:
        data = cfg(member.guild.id)
        if not data.get("channel_id"):
            return "run /setup and choose Welcome first."
        channel = member.guild.get_channel(int(data["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return "welcome channel is gone."
        line, embed = self.build(member, data)
        try:
            await channel.send(line, embed=embed)
        except discord.Forbidden:
            return "bot can't send in that channel."
        return None

    @app_commands.command(name="welcometest", description="send a welcome preview as if you just joined")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcometest(self, interaction: discord.Interaction, member: discord.Member | None = None):
        err = await self.send_welcome(member or interaction.user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await interaction.response.send_message("sent preview.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self.send_welcome(member)

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
