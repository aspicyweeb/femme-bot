import discord
from discord import app_commands
from discord.ext import commands

import storage


def entry(table: dict, key: str) -> dict:
    raw = table.get(key, 0)
    if isinstance(raw, dict):
        try:
            total = float(raw.get("total") or 0)
        except (TypeError, ValueError):
            total = 0.0
        return {"name": str(raw.get("name") or key), "total": total}
    try:
        total = float(raw or 0)
    except (TypeError, ValueError):
        total = 0.0
    return {"name": key, "total": total}


def _person(member: discord.Member | None, name: str | None) -> tuple[str, str, str]:
    if member is not None:
        label = member.mention
        key = str(member.id)
        display = member.display_name
        if name and name.strip():
            display = name.strip()[:80]
        return key, label, display
    if name and name.strip():
        clean = name.strip()[:80]
        return f"name:{clean.lower()}", clean, clean
    raise ValueError("Pick a member, or type a name if they are not in the server.")


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="autorole", description="Role given when someone joins")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Role to give new members")
    async def autorole(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        if role.is_default() or role.managed:
            await interaction.response.send_message("That role can't be assigned.", ephemeral=True)
            return
        async with storage.lock:
            data = storage.load_obj("config.json")
            guild = str(interaction.guild_id)
            data.setdefault(guild, {})
            data[guild]["autorole"] = role.id
            storage.save("config.json", data)
        note = ""
        me = interaction.guild.me
        if me is not None and role >= me.top_role:
            note = " Move my role above it or I can't assign it."
        await interaction.response.send_message(f"New members get {role.mention}.{note}", ephemeral=True)

    @app_commands.command(name="setlogs", description="Channels for joins, deleted messages, and server changes")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        members="Joins, leaves, roles, bans",
        messages="Deleted and edited messages",
        events="Role, channel, and server changes",
    )
    async def setlogs(
        self,
        interaction: discord.Interaction,
        members: discord.TextChannel | None = None,
        messages: discord.TextChannel | None = None,
        events: discord.TextChannel | None = None,
    ):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        updates: dict[str, int] = {}
        shown: list[str] = []
        if members is not None:
            updates["members"] = members.id
            shown.append(f"members {members.mention}")
        if messages is not None:
            updates["messages"] = messages.id
            shown.append(f"messages {messages.mention}")
        if events is not None:
            updates["random"] = events.id
            shown.append(f"events {events.mention}")
        if not updates:
            await interaction.response.send_message("Pick at least one channel.", ephemeral=True)
            return
        async with storage.lock:
            data = storage.load_obj("config.json")
            guild = str(interaction.guild_id)
            data.setdefault(guild, {})
            logs = data[guild].setdefault("logs", {})
            logs.update(updates)
            storage.save("config.json", data)
        await interaction.response.send_message("Logging set: " + ", ".join(shown), ephemeral=True)

    @app_commands.command(name="setverify", description="Roles for unverified, 18+, and creator")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        unverified="Role people have before they verify",
        verified="18+ role",
        creator="Creator role",
    )
    async def setverify(
        self,
        interaction: discord.Interaction,
        unverified: discord.Role | None = None,
        verified: discord.Role | None = None,
        creator: discord.Role | None = None,
    ):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        updates: dict[str, int] = {}
        shown: list[str] = []
        if unverified is not None:
            updates["unverified"] = unverified.id
            shown.append(f"unverified {unverified.mention}")
        if verified is not None:
            updates["18"] = verified.id
            shown.append(f"18+ {verified.mention}")
        if creator is not None:
            updates["creator"] = creator.id
            shown.append(f"creator {creator.mention}")
        if not updates:
            await interaction.response.send_message("Pick at least one role.", ephemeral=True)
            return
        async with storage.lock:
            data = storage.load_obj("config.json")
            guild = str(interaction.guild_id)
            data.setdefault(guild, {})
            verify = data[guild].setdefault("verify", {})
            verify.update(updates)
            storage.save("config.json", data)
        await interaction.response.send_message("Verification set: " + ", ".join(shown), ephemeral=True)

    async def _change(
        self,
        interaction: discord.Interaction,
        action: str,
        amount: float,
        member: discord.Member | None,
        name: str | None,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        try:
            key, label, display = _person(member, name)
            amount = round(float(amount), 2)
            if amount <= 0:
                raise ValueError("Amount has to be more than 0.")
            async with storage.lock:
                data = storage.load_obj("sent.json")
                guild = str(interaction.guild_id)
                table = data.setdefault(guild, {})
                if not isinstance(table, dict):
                    table = {}
                current = entry(table, key)
                if action == "sent":
                    total = round(current["total"] + amount, 2)
                    table[key] = {"name": display, "total": total}
                    msg = f"+${amount:.2f} {label} · total ${total:.2f}"
                else:
                    total = round(current["total"] - amount, 2)
                    if total <= 0:
                        table.pop(key, None)
                        total = 0
                    else:
                        table[key] = {"name": current["name"] or display, "total": total}
                    msg = f"-${amount:.2f} {label} · total ${total:.2f}"
                data[guild] = table
                storage.save("sent.json", data)
        except (ValueError, storage.DataError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="sent", description="Add to someone's sent total")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(amount="Dollars", member="Someone in the server", name="Name if they are not in the server")
    async def sent(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[float, 0.01, 1000000000.0],
        member: discord.Member | None = None,
        name: str | None = None,
    ):
        await self._change(interaction, "sent", amount, member, name)

    @app_commands.command(name="sentremove", description="Subtract from someone's sent total")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(amount="Dollars", member="Someone in the server", name="Name if they are not in the server")
    async def sentremove(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[float, 0.01, 1000000000.0],
        member: discord.Member | None = None,
        name: str | None = None,
    ):
        await self._change(interaction, "remove", amount, member, name)

    @app_commands.command(name="sentreset", description="Wipe the sent leaderboard")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def sentreset(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        async with storage.lock:
            data = storage.load_obj("sent.json")
            data[str(interaction.guild_id)] = {}
            storage.save("sent.json", data)
        await interaction.response.send_message("Leaderboard wiped.", ephemeral=True)

    @app_commands.command(name="leaderboard", description="Sent totals")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def leaderboard(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        data = storage.load_obj("sent.json")
        table = data.get(str(interaction.guild_id), {})
        if not isinstance(table, dict) or not table:
            await interaction.response.send_message("Empty.", ephemeral=True)
            return
        rows = []
        for key in table:
            item = entry(table, key)
            rows.append((key, item["name"], item["total"]))
        rows.sort(key=lambda row: row[2], reverse=True)
        lines = []
        for i, (key, saved_name, total) in enumerate(rows[:25], start=1):
            shown = f"<@{key}>" if str(key).isdigit() else saved_name
            lines.append(f"**{i}.** {shown} — ${total:.2f}")
        grand = sum(row[2] for row in rows)
        await interaction.response.send_message("\n".join(lines) + f"\n\ntotal ${grand:.2f}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Setup(bot))
