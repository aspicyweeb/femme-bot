import logging

import discord
from discord import app_commands
from discord.ext import commands

import storage

log = logging.getLogger(__name__)
COLOR = 0xC9A0FF


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
            title=fill(data.get("title") or f"welcome to {member.guild.name}", member)[:256],
            description=fill(data.get("body") or "you made it.", member)[:4096],
            color=COLOR,
        )
        thumb = (data.get("image") or "").strip()
        if thumb:
            embed.set_thumbnail(url=thumb)
        banner = (data.get("banner") or "").strip()
        if banner:
            embed.set_image(url=banner)
        return line[:2000], embed

    async def send_welcome(self, member: discord.Member) -> str | None:
        try:
            data = storage.load_obj("config.json").get(str(member.guild.id), {}).get("welcome", {})
        except storage.DataError as exc:
            return str(exc)
        if not isinstance(data, dict) or not data.get("channel_id"):
            return "Welcome not set up. Use /welcomesetup."
        channel = member.guild.get_channel(int(data["channel_id"]))
        if channel is None:
            try:
                channel = await member.guild.fetch_channel(int(data["channel_id"]))
            except (discord.Forbidden, discord.HTTPException):
                return "Welcome channel is gone."
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return "Welcome channel is gone."
        line, embed = self.build(member, data)
        try:
            await channel.send(line, embed=embed)
        except discord.Forbidden:
            return "Bot can't send in that channel."
        except discord.HTTPException as exc:
            return f"Couldn't send welcome: {exc}"
        return None

    @app_commands.command(name="welcomesetup", description="Set the welcome channel and messages")
    @app_commands.describe(
        channel="Channel to send welcomes in",
        line="Message above the embed. {user} {name} {server} {count}",
        title="Embed title",
        body="Embed description",
        image="Thumbnail URL (optional)",
        banner="Big image URL (optional)",
    )
    @app_commands.guild_only()
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
        try:
            async with storage.lock:
                data = storage.load_obj("config.json")
                guild = str(interaction.guild_id)
                data.setdefault(guild, {})
                welcome = data[guild].setdefault("welcome", {})
                welcome["channel_id"] = channel.id
                welcome["line"] = line[:2000]
                welcome["title"] = title[:256]
                welcome["body"] = body[:4000]
                if image and image.strip():
                    welcome["image"] = image.strip()
                else:
                    welcome.pop("image", None)
                if banner and banner.strip():
                    welcome["banner"] = banner.strip()
                else:
                    welcome.pop("banner", None)
                storage.save("config.json", data)
        except storage.DataError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Welcome set for {channel.mention}. Use /welcometest to preview.",
            ephemeral=True,
        )

    @app_commands.command(name="welcometest", description="Send a welcome preview")
    @app_commands.describe(member="Who to preview. Defaults to you.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def welcometest(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        err = await self.send_welcome(target)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await interaction.response.send_message("Sent preview.", ephemeral=True)

    @app_commands.command(name="welcomeoff", description="Turn off welcome messages")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomeoff(self, interaction: discord.Interaction):
        try:
            async with storage.lock:
                data = storage.load_obj("config.json")
                guild = str(interaction.guild_id)
                if guild in data and isinstance(data[guild], dict):
                    data[guild].pop("welcome", None)
                    storage.save("config.json", data)
        except storage.DataError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message("Welcome turned off.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        err = await self.send_welcome(member)
        if err and "not set up" not in err:
            log.warning("welcome: %s", err)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
