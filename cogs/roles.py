import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "panels.json"
DRAFT_FILE = Path(__file__).resolve().parent.parent / "data" / "drafts.json"
DEFAULT_EMOJIS = ["✅", "❌", "💗", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def load_json(path: Path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def draft_key(guild_id: int, user_id: int) -> str:
    return f"{guild_id}:{user_id}"


def emoji_key(emoji) -> str:
    if isinstance(emoji, str):
        return react_token(emoji)
    if getattr(emoji, "id", None):
        return str(emoji.id)
    return str(emoji)


def react_token(raw: str) -> str:
    """Turn <:name:id> / <a:name:id> into name:id so add_reaction accepts it."""
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        inner = raw[1:-1]
        parts = inner.split(":")
        if len(parts) >= 2 and parts[-1].isdigit():
            return f"{parts[-2]}:{parts[-1]}"
    return raw


def store_keys(raw: str) -> list[str]:
    token = react_token(raw)
    keys = {raw.strip(), token}
    if ":" in token:
        keys.add(token.split(":")[-1])
    return [k for k in keys if k]


def map_emoji(mapping: dict, raw: str, role_id: int) -> None:
    for key in store_keys(raw):
        mapping[key] = role_id


def display_emoji(raw: str) -> str:
    raw = raw.strip()
    animated = raw.startswith("<a:")
    token = react_token(raw)
    if ":" in token:
        name, eid = token.rsplit(":", 1)
        if eid.isdigit():
            return f"<{('a' if animated else '')}:{name}:{eid}>"
    return raw


def build_embed(title: str, rows: list, color: int) -> discord.Embed:
    lines = ["♡━━━━━━━━━━━━━━━━━━━━♡", ""]
    for row in rows:
        shown = row.get("display") or display_emoji(row["emoji"])
        lines.append(f"{shown}   ›  <@&{row['role_id']}>")
    lines += ["", "♡━━━━━━━━━━━━━━━━━━━━♡"]
    embed = discord.Embed(title=title, description="\n".join(lines), color=color)
    embed.set_footer(text="tap a reaction to take the role/roles that are relevant to you")
    return embed


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def panels(self) -> dict:
        return load_json(DATA_FILE, {"panels": {}})

    def save_panels(self, data: dict) -> None:
        save_json(DATA_FILE, data)

    def drafts(self) -> dict:
        return load_json(DRAFT_FILE, {})

    def save_drafts(self, data: dict) -> None:
        save_json(DRAFT_FILE, data)

    @app_commands.command(name="setup", description="Start a new role panel. Bot writes the embed.")
    @app_commands.describe(title="e.g. sub roles", exclusive="Only one role at a time", color="Hex like #c9a0ff")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def setup(self, interaction: discord.Interaction, title: str, exclusive: bool = False, color: str = "#c9a0ff"):
        try:
            color_int = int(color.lstrip("#"), 16)
        except ValueError:
            await interaction.response.send_message("Color must look like #c9a0ff", ephemeral=True)
            return
        drafts = self.drafts()
        drafts[draft_key(interaction.guild_id, interaction.user.id)] = {
            "title": title,
            "exclusive": exclusive,
            "color": color_int,
            "rows": [],
        }
        self.save_drafts(drafts)
        await interaction.response.send_message(
            f"Draft: **{title}** · exclusive=`{exclusive}`\n`/add` roles, then `/publish`.",
            ephemeral=True,
        )

    @app_commands.command(name="add", description="Add one role to your draft")
    @app_commands.describe(role="Role people get", emoji="Leave blank to auto-number")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add(self, interaction: discord.Interaction, role: discord.Role, emoji: str | None = None):
        drafts = self.drafts()
        key = draft_key(interaction.guild_id, interaction.user.id)
        draft = drafts.get(key)
        if not draft:
            await interaction.response.send_message("No draft. `/setup` first.", ephemeral=True)
            return
        if interaction.guild.me.top_role <= role:
            await interaction.response.send_message(f"Move the bot role above **{role.name}**.", ephemeral=True)
            return
        used = {row["emoji"] for row in draft["rows"]}
        chosen = react_token(emoji) if emoji else next((e for e in DEFAULT_EMOJIS if e not in used), None)
        if not chosen:
            await interaction.response.send_message("Panel full. Publish and start another.", ephemeral=True)
            return
        draft["rows"].append({"emoji": chosen, "role_id": role.id})
        self.save_drafts(drafts)
        await interaction.response.send_message(
            content=f"Added {chosen} → {role.mention} ({len(draft['rows'])})",
            embed=build_embed(draft["title"], draft["rows"], draft["color"]),
            ephemeral=True,
        )

    @app_commands.command(name="clear", description="Throw away the current draft")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def clear(self, interaction: discord.Interaction):
        drafts = self.drafts()
        drafts.pop(draft_key(interaction.guild_id, interaction.user.id), None)
        self.save_drafts(drafts)
        await interaction.response.send_message("Draft cleared.", ephemeral=True)

    @app_commands.command(name="publish", description="Post the finished panel")
    @app_commands.describe(channel="Where members pick roles")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def publish(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        drafts = self.drafts()
        key = draft_key(interaction.guild_id, interaction.user.id)
        draft = drafts.get(key)
        if not draft or not draft["rows"]:
            await interaction.followup.send("Draft empty.", ephemeral=True)
            return
        embed = build_embed(draft["title"], draft["rows"], draft["color"])
        try:
            msg = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("Missing access to that channel.", ephemeral=True)
            return
        mapping = {}
        for row in draft["rows"]:
            token = react_token(row["emoji"])
            try:
                await msg.add_reaction(token)
            except discord.HTTPException:
                await interaction.followup.send(
                    f"Couldn't react with {row['emoji']}. Use an emoji from this server, or one from a server the bot is in.",
                    ephemeral=True,
                )
                return
            map_emoji(mapping, row["emoji"], row["role_id"])
        data = self.panels()
        data["panels"][str(msg.id)] = {
            "channel_id": channel.id,
            "exclusive": draft["exclusive"],
            "map": mapping,
        }
        self.save_panels(data)
        drafts.pop(key, None)
        self.save_drafts(drafts)
        await interaction.followup.send(f"Live in {channel.mention}", ephemeral=True)

    @app_commands.command(name="reactrole", description="Post a reaction-role panel")
    @app_commands.describe(
        channel="Channel to post in",
        title="Panel title",
        exclusive="Only one role at a time?",
        roles="Mention roles: @owned @unowned @loser",
        emojis="Optional. Same order as roles. Custom server emotes work.",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def quick(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        roles: str,
        exclusive: bool = False,
        emojis: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        found = []
        for mention in roles.split():
            if mention.startswith("<@&") and mention.endswith(">"):
                rid = mention[3:-1]
                if rid.isdigit():
                    role = interaction.guild.get_role(int(rid))
                    if role:
                        found.append(role)
        if not found:
            await interaction.followup.send("Mention the roles in the roles field.", ephemeral=True)
            return
        if len(found) > 13:
            await interaction.followup.send("Max 13 per panel. Split into pages.", ephemeral=True)
            return
        too_high = [r.name for r in found if interaction.guild.me.top_role <= r]
        if too_high:
            await interaction.followup.send("Move the bot role above: " + ", ".join(too_high), ephemeral=True)
            return
        custom = emojis.split() if emojis else []
        if custom and len(custom) != len(found):
            await interaction.followup.send(
                f"You listed {len(found)} roles and {len(custom)} emojis. Same count.",
                ephemeral=True,
            )
            return
        rows = []
        for i, r in enumerate(found):
            raw = custom[i] if custom else DEFAULT_EMOJIS[i]
            rows.append({"emoji": react_token(raw), "role_id": r.id})
        try:
            msg = await channel.send(embed=build_embed(title, rows, 0xC9A0FF))
        except discord.Forbidden:
            await interaction.followup.send("Missing access to that channel.", ephemeral=True)
            return
        mapping = {}
        for row in rows:
            try:
                await msg.add_reaction(row["emoji"])
            except discord.HTTPException:
                await interaction.followup.send(
                    f"Couldn't react with {row['emoji']}. Custom emotes must be from this server, or a server the bot is also in.",
                    ephemeral=True,
                )
                return
            map_emoji(mapping, row["emoji"], row["role_id"])
        data = self.panels()
        data["panels"][str(msg.id)] = {
            "channel_id": channel.id,
            "exclusive": exclusive,
            "map": mapping,
        }
        self.save_panels(data)
        await interaction.followup.send(f"Posted {len(found)} roles in {channel.mention}", ephemeral=True)

    async def toggle(self, payload: discord.RawReactionActionEvent, add: bool):
        if payload.user_id == self.bot.user.id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        panel = self.panels()["panels"].get(str(payload.message_id))
        if not panel:
            return
        key = emoji_key(payload.emoji)
        role_id = panel["map"].get(key) or panel["map"].get(str(payload.emoji))
        if not role_id:
            return
        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        if role is None or member is None:
            return
        try:
            if add:
                if panel.get("exclusive"):
                    other_ids = set(panel["map"].values()) - {role.id}
                    to_remove = [r for r in member.roles if r.id in other_ids]
                    if to_remove:
                        await member.remove_roles(*to_remove, reason="exclusive panel")
                await member.add_roles(role, reason="reaction panel")
            else:
                await member.remove_roles(role, reason="reaction panel")
        except discord.Forbidden:
            print(f"missing perms for {role} on {member}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.toggle(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.toggle(payload, add=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
