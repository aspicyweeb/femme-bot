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

def get_bimbo_cfg(guild_id: int) -> dict:
    data = load()
    return data.get(str(guild_id), {}).get("bimbolock", {})

def is_locked(guild_id: int, user_id: int) -> bool:
    return user_id in get_bimbo_cfg(guild_id).get("locked", [])

def set_locked(guild_id: int, user_id: int, locked: bool) -> None:
    data = load()
    guild = str(guild_id)
    data.setdefault(guild, {})
    cfg = data[guild].setdefault("bimbolock", {})
    locked_list = cfg.setdefault("locked", [])
    if locked and user_id not in locked_list:
        locked_list.append(user_id)
    elif not locked and user_id in locked_list:
        locked_list.remove(user_id)
    save(data)

def bimboify(text: str) -> str:
    if not text:
        return text

    # basic valley/bimbo replacements
    replacements = [
        (r'\bvery\b', 'sooo'),
        (r'\breally\b', 'like really'),
        (r'\byes\b', 'yesss'),
        (r'\bno\b', 'nooo'),
        (r'\bokay\b', 'okaaay'),
        (r'\bwhat\b', 'whaaat'),
        (r'\bwhy\b', 'whyyy'),
        (r'\bhello\b', 'hiii'),
        (r'\bhi\b', 'hiii'),
        (r'\bhey\b', 'heyyy'),
        (r'\bgood\b', 'so good'),
        (r'\bbad\b', 'so bad'),
        (r'\bcool\b', 'so fetch'),
        (r'\bnice\b', 'so cute'),
        (r'\bwhatever\b', 'whateverrr'),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # insert "like" randomly
    words = text.split()
    result = []
    for i, w in enumerate(words):
        if len(w) > 2 and hash(w + str(i)) % 4 == 0:
            result.append("like")
        result.append(w)
    text = " ".join(result)

    # stretch some words
    text = re.sub(r'\b(so|really|totally|literally)\b', lambda m: m.group(0) + "o" * (hash(m.group(0)) % 3), text, flags=re.IGNORECASE)

    # cute ending
    if not any(text.lower().endswith(e) for e in ("♥", "~", "!", "?")):
        endings = [" ♥", " ~", " omg", " like literally", " xoxo", " so fetch"]
        text += endings[hash(text) % len(endings)]

    return text

class BimboLock(commands.Cog):
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
            hook = await channel.create_webhook(name="bimbolock")
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

        bimbo_text = bimboify(message.content)
        webhook = await self.get_webhook(message.channel)

        try:
            await message.delete()
        except discord.Forbidden:
            return

        try:
            if webhook:
                await webhook.send(
                    content=bimbo_text,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await message.channel.send(
                    f"**{message.author.display_name}**: {bimbo_text}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.Forbidden:
            pass

    @app_commands.command(name="bimbolock", description="Force a member to speak in bimbo until unlocked")
    @app_commands.describe(member="Member to lock into bimbo speak")
    @app_commands.checks.has_permissions(administrator=True)
    async def bimbolock(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("You can't bimbolock yourself, silly~", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("Can't bimbolock a bot.", ephemeral=True)

        set_locked(interaction.guild_id, member.id, True)
        await interaction.response.send_message(
            f"Locked {member.mention} into bimbo speak. They'll stay locked until unlocked.",
            ephemeral=True,
        )

    @app_commands.command(name="bimbounlock", description="Remove bimbo lock from a member")
    @app_commands.describe(member="Member to unlock")
    @app_commands.checks.has_permissions(administrator=True)
    async def bimbounlock(self, interaction: discord.Interaction, member: discord.Member):
        set_locked(interaction.guild_id, member.id, False)
        await interaction.response.send_message(
            f"Unlocked {member.mention} from bimbo speak.",
            ephemeral=True,
        )

    @app_commands.command(name="bimbolocks", description="List members currently bimbolocked")
    @app_commands.checks.has_permissions(administrator=True)
    async def bimbolocks(self, interaction: discord.Interaction):
        cfg = get_bimbo_cfg(interaction.guild_id)
        locked = cfg.get("locked", [])
        if not locked:
            return await interaction.response.send_message("No one is bimbolocked right now.", ephemeral=True)

        lines = []
        for uid in locked:
            member = interaction.guild.get_member(uid)
            name = member.mention if member else f"`{uid}`"
            lines.append(name)

        embed = discord.Embed(
            title="Bimbolocked Members",
            description="\n".join(lines),
            color=PASTEL_PINK,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BimboLock(bot))