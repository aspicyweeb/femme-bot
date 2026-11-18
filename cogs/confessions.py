import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_confessions_cfg(guild_id: int) -> dict:
    data = load()
    return data.get(str(guild_id), {}).get("confessions", {})

class ConfessionModal(discord.ui.Modal, title="Anonymous Confession"):
    confession = discord.ui.TextInput(
        label="Your confession",
        style=discord.TextStyle.paragraph,
        placeholder="Type your confession here...",
        max_length=1900,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_confessions_cfg(interaction.guild_id)
        channel_id = cfg.get("channel_id")
        log_channel_id = cfg.get("log_channel_id")

        if not channel_id:
            return await interaction.response.send_message(
                "Confessions aren't set up yet. Ask an admin to run `/confessionsetup`.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "The confession channel is missing. Ask an admin to re-set it.",
                ephemeral=True,
            )

        text = self.confession.value.strip()

        # Public anonymous post
        embed = discord.Embed(
            description=text,
            color=0xC9A0FF,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name="Anonymous Confession")
        embed.set_footer(text="Posted anonymously")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I don't have permission to post in the confession channel.",
                ephemeral=True,
            )

        # Admin log (spoilered)
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if isinstance(log_channel, discord.TextChannel):
                log_embed = discord.Embed(
                    title="Confession Log",
                    description=f"||{text}||",
                    color=0xFF6B6B,
                    timestamp=discord.utils.utcnow(),
                )
                log_embed.add_field(
                    name="Submitted by",
                    value=f"{interaction.user.mention} (`{interaction.user.id}`)",
                    inline=False,
                )
                log_embed.set_footer(text="Admin only • Click spoiler to reveal")
                try:
                    await log_channel.send(embed=log_embed)
                except discord.Forbidden:
                    pass  # silently fail if no perms

        await interaction.response.send_message("Confession posted anonymously.", ephemeral=True)

class Confessions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="confess", description="Submit an anonymous confession")
    async def confess(self, interaction: discord.Interaction):
        if not get_confessions_cfg(interaction.guild_id).get("channel_id"):
            return await interaction.response.send_message(
                "Confessions aren't set up yet.",
                ephemeral=True,
            )
        await interaction.response.send_modal(ConfessionModal())

    @app_commands.command(name="confessionsetup", description="Set the channels for anonymous confessions")
    @app_commands.describe(
        channel="Public channel where confessions are posted",
        log_channel="Admin-only channel for logs (optional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def confessionsetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        log_channel: discord.TextChannel | None = None,
    ):
        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        conf = data[guild].setdefault("confessions", {})
        conf["channel_id"] = channel.id
        if log_channel:
            conf["log_channel_id"] = log_channel.id
        else:
            conf.pop("log_channel_id", None)
        save(data)

        msg = f"Confessions will be posted in {channel.mention}."
        if log_channel:
            msg += f"\nLogs will go to {log_channel.mention} (spoilered)."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="confessionoff", description="Disable anonymous confessions")
    @app_commands.checks.has_permissions(administrator=True)
    async def confessionoff(self, interaction: discord.Interaction):
        data = load()
        guild = str(interaction.guild_id)
        if guild in data and "confessions" in data[guild]:
            del data[guild]["confessions"]
            save(data)
        await interaction.response.send_message("Confessions disabled.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Confessions(bot))