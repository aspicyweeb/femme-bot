import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "sent.json"


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def entry(table: dict, key: str) -> dict:
    raw = table.get(key, 0)
    if isinstance(raw, dict):
        return {"name": raw.get("name") or key, "total": float(raw.get("total") or 0)}
    return {"name": key, "total": float(raw or 0)}


class Sent(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sent", description="add a dollar amount someone sent")
    @app_commands.describe(
        amount="dollar amount like 10 or 10.50",
        user="discord user if they have one. does not have to be in the server",
        name="name to track if they are not on discord",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sent(
        self,
        interaction: discord.Interaction,
        amount: float,
        user: discord.User | None = None,
        name: str | None = None,
    ):
        if amount == 0:
            await interaction.response.send_message("amount can't be 0.", ephemeral=True)
            return
        if user is None and not (name and name.strip()):
            await interaction.response.send_message("pick a user or type a name.", ephemeral=True)
            return
        key = str(user.id) if user else f"name:{name.strip().lower()}"
        label = user.mention if user else name.strip()
        data = load()
        table = data.setdefault(str(interaction.guild_id), {})
        current = entry(table, key)
        total = round(current["total"] + amount, 2)
        table[key] = {"name": user.display_name if user else name.strip(), "total": total}
        data[str(interaction.guild_id)] = table
        save(data)
        await interaction.response.send_message(
            f"+${amount:.2f} {label} · total ${total:.2f}",
            ephemeral=True,
        )

    @app_commands.command(name="leaderboard", description="list totals people have sent")
    @app_commands.checks.has_permissions(administrator=True)
    async def leaderboard(self, interaction: discord.Interaction):
        table = load().get(str(interaction.guild_id), {})
        if not table:
            await interaction.response.send_message("empty.", ephemeral=True)
            return
        rows = []
        for key, raw in table.items():
            item = entry(table, key)
            rows.append((key, item["name"], item["total"]))
        rows.sort(key=lambda r: r[2], reverse=True)
        lines = []
        for i, (key, saved_name, total) in enumerate(rows[:25], start=1):
            if key.isdigit():
                member = interaction.guild.get_member(int(key))
                shown = member.mention if member else saved_name
            else:
                shown = saved_name
            lines.append(f"**{i}.** {shown} — ${total:.2f}")
        grand = sum(r[2] for r in rows)
        await interaction.response.send_message(
            ("\n".join(lines) + f"\n\ntotal ${grand:.2f}")[:1900]
        )

    @app_commands.command(name="sentremove", description="subtract an amount from someone")
    @app_commands.describe(amount="amount to take off", user="discord user", name="name if they are not on discord")
    @app_commands.checks.has_permissions(administrator=True)
    async def sentremove(
        self,
        interaction: discord.Interaction,
        amount: float,
        user: discord.User | None = None,
        name: str | None = None,
    ):
        if user is None and not (name and name.strip()):
            await interaction.response.send_message("pick a user or type a name.", ephemeral=True)
            return
        key = str(user.id) if user else f"name:{name.strip().lower()}"
        label = user.mention if user else name.strip()
        data = load()
        table = data.setdefault(str(interaction.guild_id), {})
        current = entry(table, key)
        total = round(current["total"] - abs(amount), 2)
        if total <= 0:
            table.pop(key, None)
            total = 0
        else:
            table[key] = {"name": current["name"], "total": total}
        data[str(interaction.guild_id)] = table
        save(data)
        await interaction.response.send_message(
            f"-${abs(amount):.2f} {label} · total ${total:.2f}",
            ephemeral=True,
        )

    @app_commands.command(name="sentreset", description="wipe the whole leaderboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def sentreset(self, interaction: discord.Interaction):
        data = load()
        data[str(interaction.guild_id)] = {}
        save(data)
        await interaction.response.send_message("leaderboard wiped.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Sent(bot))
