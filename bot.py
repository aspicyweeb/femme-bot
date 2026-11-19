import os
import logging
import traceback
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.reactions = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.tree.command(name="ping", description="test if the bot answers")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)

@bot.event
async def setup_hook():
    cogs_dir = Path(__file__).parent / "cogs"
    for file in cogs_dir.glob("*.py"):
        if file.name.startswith("_"):
            continue
        if file.stem in {"lockdown", "tickets"}:
            continue
        try:
            await bot.load_extension(f"cogs.{file.stem}")
            print(f"loaded cog {file.stem}")
        except Exception as e:
            print(f"FAILED cog {file.stem}: {e}")
            traceback.print_exc()

    # Make every command admin-only
    for cmd in bot.tree.walk_commands():
        cmd.default_permissions = discord.Permissions(administrator=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    cmd_name = interaction.command.name if interaction.command else "unknown"
    print(f"Command error in /{cmd_name}:")
    traceback.print_exc()
    try:
        msg = f"Something broke: {original}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

@bot.event
async def on_ready():
    print(f"logged in as {bot.user} ({bot.user.id})")
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.clear_commands(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"synced {len(synced)} commands to guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"synced {len(synced)} commands globally")
        print("commands:", ", ".join(sorted(c.name for c in bot.tree.walk_commands())))
    except Exception as e:
        print("slash sync failed:", e)
        traceback.print_exc()
    print("cogs:", ", ".join(bot.cogs))

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in .env")
    bot.run(TOKEN)