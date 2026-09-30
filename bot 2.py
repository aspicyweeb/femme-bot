import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.reactions = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.tree.interaction_check
async def admin_slash_only(interaction: discord.Interaction) -> bool:
    if interaction.type != discord.InteractionType.application_command:
        return True
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    await interaction.response.send_message("Administrator only.", ephemeral=True)
    return False


@bot.event
async def on_ready():
    print(f"logged in as {bot.user} ({bot.user.id})")
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        print(f"synced {len(synced)} slash commands")
    except Exception as e:
        print("slash sync failed:", e)
    print("cogs:", ", ".join(bot.cogs))


@bot.event
async def setup_hook():
    cogs_dir = Path(__file__).parent / "cogs"
    for file in cogs_dir.glob("*.py"):
        if file.name.startswith("_"):
            continue
        await bot.load_extension(f"cogs.{file.stem}")
        print(f"loaded cog {file.stem}")
    perms = discord.Permissions(administrator=True)
    for cmd in bot.tree.walk_commands():
        cmd.default_permissions = perms


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in .env")
    bot.run(TOKEN)
