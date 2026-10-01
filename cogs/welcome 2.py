import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "welcome.json"
COLOR = 0xC9A0FF


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
            return "run /welcomesetup first."
        channel = member.guild.get_channel(int(data["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return "welcome channel is gone."
        line, embed = self.build(member, data)
        try:
            await channel.send(line, embed=embed)
        except discord.Forbidden:
            return "bot can't send in that channel."
        return None

    @app_commands.command(name="welcomesetup", description="set welcome channel and embed fields")
    @app_commands.describe(
        channel="channel to post welcomes",
        line="plain text above the embed. use {user} for the mention",
        title="embed title",
        body="embed text. you can paste channel mentions",
        image="cdn link from /imagelink. small picture on the right",
        banner="cdn link from /imagelink. big image under the text",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomesetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        line: str = "hi there {user}! 💎",
        title: str = "welcome to {server}",
        body: str = "you made it.",
        image: str | None = None,
        banner: str | None = None,
    ):
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry.update(
            {
                "channel_id": channel.id,
                "line": line[:200],
                "title": title[:256],
                "body": body[:4000],
                "image": (image or entry.get("image") or "").strip(),
                "banner": (banner or entry.get("banner") or "").strip(),
            }
        )
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message(f"welcome set for {channel.mention}. use /welcometest to preview.", ephemeral=True)

    @app_commands.command(name="welcomeimage", description="set the welcome thumbnail from an imagelink url")
    @app_commands.describe(url="paste the cdn link from /imagelink")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomeimage(self, interaction: discord.Interaction, url: str):
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry["image"] = url.strip()
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message("welcome image saved.", ephemeral=True)

    @app_commands.command(name="welcomebanner", description="set the big image under the welcome text")
    @app_commands.describe(url="paste the cdn link from /imagelink")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomebanner(self, interaction: discord.Interaction, url: str):
        data = load()
        entry = data.get(str(interaction.guild_id), {})
        entry["banner"] = url.strip()
        data[str(interaction.guild_id)] = entry
        save(data)
        await interaction.response.send_message("welcome banner saved.", ephemeral=True)

    @app_commands.command(name="welcomeoff", description="stop welcome messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomeoff(self, interaction: discord.Interaction):
        data = load()
        data.pop(str(interaction.guild_id), None)
        save(data)
        await interaction.response.send_message("welcome off.", ephemeral=True)

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
