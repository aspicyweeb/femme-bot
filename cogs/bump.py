import asyncio
import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "bump.json"
DEFAULT_HOURS = 2
DEFAULT_TEXT = "time to `/bump`"


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class Bump(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @app_commands.command(name="bumpsetup", description="set the bump reminder channel and interval")
    @app_commands.describe(
        channel="where the reminder posts",
        hours="hours between reminders. default 2",
        role="optional role to ping",
        text="optional custom reminder text",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def bumpsetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        hours: float = DEFAULT_HOURS,
        role: discord.Role | None = None,
        text: str | None = None,
    ):
        if hours <= 0 or hours > 168:
            await interaction.response.send_message("hours must be between 0 and 168.", ephemeral=True)
            return
        data = load()
        data[str(interaction.guild_id)] = {
            "channel_id": channel.id,
            "hours": hours,
            "role_id": role.id if role else None,
            "text": (text or DEFAULT_TEXT)[:1800],
            "next": 0,
        }
        save(data)
        await interaction.response.send_message(
            f"bump reminder every {hours}h in {channel.mention}"
            + (f" pinging {role.mention}" if role else ""),
            ephemeral=True,
        )

    @app_commands.command(name="bumpoff", description="stop bump reminders")
    @app_commands.checks.has_permissions(administrator=True)
    async def bumpoff(self, interaction: discord.Interaction):
        data = load()
        data.pop(str(interaction.guild_id), None)
        save(data)
        await interaction.response.send_message("bump reminders off.", ephemeral=True)

    @app_commands.command(name="bumpnow", description="send the bump reminder now and reset the timer")
    @app_commands.checks.has_permissions(administrator=True)
    async def bumpnow(self, interaction: discord.Interaction):
        sent = await self.post(interaction.guild)
        if not sent:
            await interaction.response.send_message("run /bumpsetup first.", ephemeral=True)
            return
        await interaction.response.send_message("sent.", ephemeral=True)

    async def post(self, guild: discord.Guild | None) -> bool:
        if guild is None:
            return False
        data = load()
        cfg = data.get(str(guild.id))
        if not cfg:
            return False
        channel = guild.get_channel(int(cfg["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return False
        role_id = cfg.get("role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        text = cfg.get("text") or DEFAULT_TEXT
        if role:
            content = f"{role.mention} {text}"
        else:
            content = text
        try:
            await channel.send(content)
        except discord.Forbidden:
            print("bump: missing send perms")
            return False
        import time
        cfg["next"] = time.time() + float(cfg.get("hours") or DEFAULT_HOURS) * 3600
        data[str(guild.id)] = cfg
        save(data)
        return True

    @tasks.loop(minutes=1)
    async def loop(self):
        import time
        now = time.time()
        data = load()
        changed = False
        for gid, cfg in list(data.items()):
            nxt = float(cfg.get("next") or 0)
            if nxt and now < nxt:
                continue
            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue
            await self.post(guild)
            changed = True
        if changed:
            pass

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Bump(bot))
END
