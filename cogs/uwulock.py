import json
import re
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path("/data/config.json")
PASTEL_PINK = 0xFFB6C1

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_uwu_cfg(guild_id: int) -> dict:
    data = load()
    return data.get(str(guild_id), {}).get("uwulock", {})

def is_locked(guild_id: int, user_id: int) -> bool:
    return user_id in get_uwu_cfg(guild_id).get("locked", [])

def set_locked(guild_id: int, user_id: int, locked: bool) -> None:
    data = load()
    guild = str(guild_id)
    data.setdefault(guild, {})
    cfg = data[guild].setdefault("uwulock", {})
    locked_list = cfg.setdefault("locked", [])
    if locked and user_id not in locked_list:
        locked_list.append(user_id)
    elif not locked and user_id in locked_list:
        locked_list.remove(user_id)
    save(data)

def uwuify(text: str) -> str:
    if not text:
        return text

    # basic uwu rules
    text = re.sub(r'[rl]', 'w', text, flags=re.IGNORECASE)
    text = re.sub(r'([nN])([aeiouAEIOU])', r'\1y\2', text)
    text = text.replace("ove", "uv").replace("OVE", "UV")
    text = text.replace("!", "!!").replace("?", "??")

    # stutter chance on words
    words = text.split()
    result = []
    for w in words:
        if len(w) > 2 and re.match(r'^[a-zA-Z]', w) and hash(w) % 4 == 0:
            result.append(f"{w[0]}-{w}")
        else:
            result.append(w)
    text = " ".join(result)

    # cute ending
    if not text.endswith(("~", "uwu", "owo", "!", "?")):
        endings = [" uwu", " owo", "~", " >w<"]
        text += endings[hash(text) % len(endings)]

    return text

class UwuLock(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.webhooks: dict[int, discord.Webhook] = {}

    async def get_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        if channel.id in self.webhooks:
            return self.webhooks[channel.id]
        try:
            hooks = await channel.webhooks()
            for hook in hooks:
                if hook.user == self.bot.user:
                    self.webhooks[channel.id] = hook
                    return hook
            hook = await channel.create_webhook(name="uwulock")
            self.webhooks[channel.id] = hook
            return hook
        except discord.Forbidden:
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        if not is_locked(message.guild.id, message.author.id):
            return

        uwu_text = uwuify(message.content)
        webhook = await self.get_webhook(message.channel)

        try:
            await message.delete()
        except discord.Forbidden:
            return

        try:
            if webhook:
                await webhook.send(
                    content=uwu_text,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await message.channel.send(
                    f"**{message.author.display_name}**: {uwu_text}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.Forbidden:
            pass

    @app_commands.command(name="uwulock", description="Force a member to speak in uwu until unlocked")
    @app_commands.describe(member="Member to lock into uwu speak")
    @app_commands.checks.has_permissions(administrator=True)
    async def uwulock(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("You can't uwulock yourself.", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("Can't uwulock a bot.", ephemeral=True)

        set_locked(interaction.guild_id, member.id, True)
        await interaction.response.send_message(
            f"Locked {member.mention} into uwu speak. They'll stay locked until unlocked.",
            ephemeral=True,
        )

    @app_commands.command(name="uwuunlock", description="Remove uwu lock from a member")
    @app_commands.describe(member="Member to unlock")
    @app_commands.checks.has_permissions(administrator=True)
    async def uwuunlock(self, interaction: discord.Interaction, member: discord.Member):
        set_locked(interaction.guild_id, member.id, False)
        await interaction.response.send_message(
            f"Unlocked {member.mention} from uwu speak.",
            ephemeral=True,
        )

    @app_commands.command(name="uwulocks", description="List members currently uwulocked")
    @app_commands.checks.has_permissions(administrator=True)
    async def uwulocks(self, interaction: discord.Interaction):
        cfg = get_uwu_cfg(interaction.guild_id)
        locked = cfg.get("locked", [])
        if not locked:
            return await interaction.response.send_message("No one is uwulocked right now.", ephemeral=True)

        lines = []
        for uid in locked:
            member = interaction.guild.get_member(uid)
            name = member.mention if member else f"`{uid}`"
            lines.append(name)

        embed = discord.Embed(
            title="Uwulocked Members",
            description="\n".join(lines),
            color=PASTEL_PINK,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(UwuLock(bot))