import logging
import os
import traceback
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import storage

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("femme-bot")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.reactions = True
if hasattr(intents, "moderation"):
    intents.moderation = True
elif hasattr(intents, "bans"):
    intents.bans = True

bot = commands.Bot(command_prefix="!", intents=intents)
_synced = False


@bot.tree.command(name="ping", description="test if the bot answers")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)


def _friendly(error: app_commands.AppCommandError) -> str:
    original = getattr(error, "original", error)
    if isinstance(error, app_commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions) or "a permission"
        return f"I'm missing {missing}."
    if isinstance(error, app_commands.MissingPermissions):
        return "You need administrator."
    if isinstance(original, discord.Forbidden):
        return "I don't have permission to do that. Move my role higher and check the channel."
    if isinstance(error, app_commands.CommandOnCooldown):
        return "Slow down a second and try again."
    if isinstance(error, app_commands.NoPrivateMessage):
        return "Use that in the server, not in DMs."
    if isinstance(error, app_commands.CheckFailure):
        return "You can't use that."
    if isinstance(error, app_commands.TransformerError):
        return "Check that option and try again. Role, channel, or user didn't resolve."
    text = f"Something broke: {original}"
    return text if len(text) <= 500 else text[:499] + "…"


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Cog handlers run first and already reply. Don't send a second message.
    if interaction.extras.get("error_reported"):
        return
    original = getattr(error, "original", error)
    cmd_name = interaction.command.name if interaction.command else "unknown"
    traceback.print_exception(type(original), original, original.__traceback__)
    log.error("command error in /%s: %s", cmd_name, original)
    try:
        msg = _friendly(error)
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        interaction.extras["error_reported"] = True
    except Exception:
        log.exception("failed to report command error")


async def _sync_guild(guild: discord.abc.Snowflake) -> None:
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    log.info("synced %s commands to guild %s", len(synced), guild.id)


async def _sync_commands() -> None:
    global _synced
    if _synced:
        return
    # Guild copies show up immediately. Same name overrides the global one,
    # so people don't see two of each command.
    for guild in list(bot.guilds):
        try:
            await _sync_guild(guild)
        except Exception:
            log.exception("guild sync failed for %s", getattr(guild, "id", guild))
    try:
        synced = await bot.tree.sync()
        names = ", ".join(sorted(c.name for c in bot.tree.get_commands()))
        log.info("synced %s commands globally: %s", len(synced), names)
        _synced = True
    except Exception:
        log.exception("slash sync failed")


@bot.event
async def setup_hook():
    storage.migrate()
    cogs_dir = Path(__file__).parent / "cogs"
    for file in sorted(cogs_dir.glob("*.py")):
        if file.name.startswith("_"):
            continue
        try:
            await bot.load_extension(f"cogs.{file.stem}")
            log.info("loaded cog %s", file.stem)
        except Exception:
            log.exception("FAILED cog %s", file.stem)

    # Hide every command from non-admins. Server settings can still override this.
    for cmd in bot.tree.walk_commands():
        cmd.default_permissions = discord.Permissions(administrator=True)


@bot.event
async def on_ready():
    log.info("logged in as %s (%s)", bot.user, bot.user.id)
    await _sync_commands()
    log.info("cogs: %s", ", ".join(bot.cogs))
    log.info("data folder: %s", storage.data_dir())


@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        await _sync_guild(guild)
    except Exception:
        log.exception("sync on join failed for %s", guild.id)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in .env")
    bot.run(TOKEN)
