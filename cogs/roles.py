import discord
from discord import app_commands
from discord.ext import commands

import storage

DEFAULT_EMOJIS = ["✅", "❌", "💗", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def react_token(raw: str) -> str:
    """Turn <:name:id> / <a:name:id> into name:id so add_reaction accepts it."""
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        parts = raw[1:-1].split(":")
        if len(parts) >= 2 and parts[-1].isdigit():
            return f"{parts[-2]}:{parts[-1]}"
    return raw


def is_animated(raw: str) -> bool:
    return raw.strip().startswith("<a:")


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
    animated = is_animated(raw)
    token = react_token(raw)
    if ":" in token:
        name, eid = token.rsplit(":", 1)
        if eid.isdigit():
            prefix = "a" if animated else ""
            return f"<{prefix}:{name}:{eid}>"
    return raw


def emoji_key(emoji) -> str:
    if isinstance(emoji, str):
        return react_token(emoji)
    if getattr(emoji, "id", None):
        return str(emoji.id)
    return str(emoji)


def build_embed(title: str, rows: list, color: int) -> discord.Embed:
    lines = ["♡━━━━━━━━━━━━━━━━━━━━♡", ""]
    for row in rows:
        shown = row.get("display") or display_emoji(row["emoji"])
        lines.append(f"{shown}   ›  <@&{row['role_id']}>")
    lines += ["", "♡━━━━━━━━━━━━━━━━━━━━♡"]
    embed = discord.Embed(title=title[:256], description="\n".join(lines)[:4096], color=color)
    embed.set_footer(text="tap a reaction to take the role/roles that are relevant to you")
    return embed


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def panels(self) -> dict:
        data = storage.load_obj("panels.json")
        if not isinstance(data.get("panels"), dict):
            data["panels"] = {}
        return data

    def save_panels(self, data: dict) -> None:
        storage.save("panels.json", data)

    async def _post_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        roles: str,
        exclusive: bool,
        emojis: str | None,
    ):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            await interaction.followup.send("Use this in the server.", ephemeral=True)
            return
        found = []
        for mention in roles.split():
            if mention.startswith("<@&") and mention.endswith(">"):
                rid = mention[3:-1]
                if rid.isdigit():
                    role = interaction.guild.get_role(int(rid))
                    if role:
                        found.append(role)
        if not found:
            await interaction.followup.send(
                "Mention the roles in the roles field, like `@owned @unowned`.",
                ephemeral=True,
            )
            return
        custom = emojis.split() if emojis else []
        limit = 20 if custom else len(DEFAULT_EMOJIS)
        if len(found) > limit:
            await interaction.followup.send(
                f"Max {limit} per panel" + ("" if custom else " unless you pass your own emojis") + ". Split it.",
                ephemeral=True,
            )
            return
        me = interaction.guild.me
        if me is None:
            await interaction.followup.send("I can't see myself in this server yet. Try again in a few seconds.", ephemeral=True)
            return
        too_high = [r.name for r in found if me.top_role <= r]
        if too_high:
            await interaction.followup.send("Move the bot role above: " + ", ".join(too_high), ephemeral=True)
            return
        managed = [r.name for r in found if r.managed or r.is_default()]
        if managed:
            await interaction.followup.send("I can't assign: " + ", ".join(managed), ephemeral=True)
            return
        if custom and len(custom) != len(found):
            await interaction.followup.send(
                f"You listed {len(found)} roles and {len(custom)} emojis. Same count.",
                ephemeral=True,
            )
            return
        rows = []
        for i, role in enumerate(found):
            raw = custom[i] if custom else DEFAULT_EMOJIS[i]
            rows.append({"emoji": react_token(raw), "role_id": role.id, "display": display_emoji(raw)})
        mapping = {}
        if custom:
            for raw, role in zip(custom, found):
                map_emoji(mapping, raw, role.id)
        else:
            for row in rows:
                map_emoji(mapping, row["emoji"], row["role_id"])
        try:
            msg = await channel.send(embed=build_embed(title, rows, 0xC9A0FF))
        except discord.Forbidden:
            await interaction.followup.send("Missing access to that channel.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(f"Couldn't post the panel: {exc}", ephemeral=True)
            return
        try:
            async with storage.lock:
                data = self.panels()
                data["panels"][str(msg.id)] = {
                    "channel_id": channel.id,
                    "exclusive": exclusive,
                    "map": mapping,
                }
                self.save_panels(data)
        except storage.DataError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        for row in rows:
            try:
                await msg.add_reaction(row["emoji"])
            except discord.HTTPException:
                try:
                    async with storage.lock:
                        data = self.panels()
                        data["panels"].pop(str(msg.id), None)
                        self.save_panels(data)
                except storage.DataError:
                    pass
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass
                await interaction.followup.send(
                    f"Couldn't react with {row['emoji']}. Custom emotes have to be from this server, or a server I'm also in.",
                    ephemeral=True,
                )
                return
        await interaction.followup.send(f"Posted {len(found)} roles in {channel.mention}", ephemeral=True)

    @app_commands.command(name="reactrole", description="post a reaction-role panel")
    @app_commands.describe(
        channel="channel to post in",
        title="panel title",
        exclusive="only one role from this panel at a time?",
        roles="mention roles: @owned @unowned @loser",
        emojis="optional. same order as roles. custom server emotes work.",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def reactrole(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        roles: str,
        exclusive: bool = False,
        emojis: str | None = None,
    ):
        await self._post_panel(interaction, channel, title, roles, exclusive, emojis)

    @app_commands.command(name="quick", description="post a reaction-role panel")
    @app_commands.describe(
        channel="channel to post in",
        title="panel title",
        exclusive="only one role from this panel at a time?",
        roles="mention roles: @owned @unowned @loser",
        emojis="optional. same order as roles. custom server emotes work.",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def quick(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        roles: str,
        exclusive: bool = False,
        emojis: str | None = None,
    ):
        await self._post_panel(interaction, channel, title, roles, exclusive, emojis)

    async def toggle(self, payload: discord.RawReactionActionEvent, add: bool):
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        try:
            panel = self.panels()["panels"].get(str(payload.message_id))
        except storage.DataError:
            return
        if not isinstance(panel, dict):
            return
        mapping = panel.get("map")
        if not isinstance(mapping, dict):
            return
        key = emoji_key(payload.emoji)
        role_id = mapping.get(key) or mapping.get(str(payload.emoji))
        if not role_id:
            return
        try:
            role = guild.get_role(int(role_id))
        except (TypeError, ValueError):
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except (discord.NotFound, discord.HTTPException):
                return
        if role is None or member is None:
            return
        try:
            if add:
                if panel.get("exclusive"):
                    other_ids = set()
                    for value in mapping.values():
                        try:
                            other_ids.add(int(value))
                        except (TypeError, ValueError):
                            continue
                    other_ids.discard(role.id)
                    to_remove = [r for r in member.roles if r.id in other_ids]
                    if to_remove:
                        await member.remove_roles(*to_remove, reason="exclusive panel")
                if role not in member.roles:
                    await member.add_roles(role, reason="reaction panel")
            elif role in member.roles:
                await member.remove_roles(role, reason="reaction panel")
        except discord.Forbidden:
            print(f"missing perms for {role} on {member}")
        except discord.HTTPException as exc:
            print(f"reaction role failed for {member}: {exc}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.toggle(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.toggle(payload, add=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
