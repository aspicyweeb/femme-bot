import json
import re
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path("/data/config.json")
PIRATE_GOLD = 0xDAA520

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_pirate_cfg(guild_id: int) -> dict:
    data = load()
    return data.get(str(guild_id), {}).get("piratelock", {})

def is_locked(guild_id: int, user_id: int) -> bool:
    return user_id in get_pirate_cfg(guild_id).get("locked", [])

def set_locked(guild_id: int, user_id: int, locked: bool) -> None:
    data = load()
    guild = str(guild_id)
    data.setdefault(guild, {})
    cfg = data[guild].setdefault("piratelock", {})
    locked_list = cfg.setdefault("locked", [])
    if locked and user_id not in locked_list:
        locked_list.append(user_id)
    elif not locked and user_id in locked_list:
        locked_list.remove(user_id)
    save(data)

def pirateify(text: str) -> str:
    if not text:
        return text

    # basic pirate replacements
    replacements = [
        (r'\byou\b', 'ye'),
        (r'\byour\b', 'yer'),
        (r'\byou\'re\b', 'ye be'),
        (r'\byou are\b', 'ye be'),
        (r'\bmy\b', 'me'),
        (r'\bis\b', 'be'),
        (r'\bare\b', 'be'),
        (r'\bthe\b', "th'"),
        (r'\bhello\b', 'ahoy'),
        (r'\bhi\b', 'ahoy'),
        (r'\bhey\b', 'ahoy'),
        (r'\bfriend\b', 'matey'),
        (r'\bfriends\b', 'mateys'),
        (r'\byes\b', 'aye'),
        (r'\bno\b', 'nay'),
        (r'\bfor\b', 'fer'),
        (r'\bto\b', "t'"),
        (r'\bof\b', "o'"),
        (r'\band\b', "an'"),
        (r'\bwhat\b', 'wha'),
        (r'\bwhere\b', 'whar'),
        (r'\bgoing\b', 'goin\''),
        (r'\bdoing\b', 'doin\''),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # random "arr" insertion
    words = text.split()
    result = []
    for w in words:
        if len(w) > 3 and re.match(r'^[a-zA-Z]', w) and hash(w) % 5 == 0:
            result.append(w + " arr")
        else:
            result.append(w)
    text = " ".join(result)

    # pirate ending
    if not any(text.lower().endswith(e) for e in ("arr", "matey", "!", "?")):
        endings = [" arr!", " matey!", " ye scurvy dog!", " ahoy!", " shiver me timbers!"]
        text += endings[hash(text) % len(endings)]

    return text

class PirateLock(commands.Cog):
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
            hook = await channel.create_webhook(name="piratelock")
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

        pirate_text = pirateify(message.content)
        webhook = await self.get_webhook(message.channel)

        try:
            await message.delete()
        except discord.Forbidden:
            return

        try:
            if webhook:
                await webhook.send(
                    content=pirate_text,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await message.channel.send(
                    f"**{message.author.display_name}**: {pirate_text}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.Forbidden:
            pass

    @app_commands.command(name="piratelock", description="Force a member to speak in pirate until unlocked")
    @app_commands.describe(member="Member to lock into pirate speak")
    @app_commands.checks.has_permissions(administrator=True)
    async def piratelock(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("Ye can't piratelock yerself, matey.", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("Can't piratelock a bot.", ephemeral=True)

        set_locked(interaction.guild_id, member.id, True)
        await interaction.response.send_message(
            f"Locked {member.mention} into pirate speak. They'll stay locked until unlocked.",
            ephemeral=True,
        )

    @app_commands.command(name="pirateunlock", description="Remove pirate lock from a member")
    @app_commands.describe(member="Member to unlock")
    @app_commands.checks.has_permissions(administrator=True)
    async def pirateunlock(self, interaction: discord.Interaction, member: discord.Member):
        set_locked(interaction.guild_id, member.id, False)
        await interaction.response.send_message(
            f"Unlocked {member.mention} from pirate speak.",
            ephemeral=True,
        )

    @app_commands.command(name="piratelocks", description="List members currently piratelocked")
    @app_commands.checks.has_permissions(administrator=True)
    async def piratelocks(self, interaction: discord.Interaction):
        cfg = get_pirate_cfg(interaction.guild_id)
        locked = cfg.get("locked", [])
        if not locked:
            return await interaction.response.send_message("No one be piratelocked right now.", ephemeral=True)

        lines = []
        for uid in locked:
            member = interaction.guild.get_member(uid)
            name = member.mention if member else f"`{uid}`"
            lines.append(name)

        embed = discord.Embed(
            title="Piratelocked Members",
            description="\n".join(lines),
            color=PIRATE_GOLD,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PirateLock(bot))