import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"
SENT_FILE = Path(__file__).resolve().parent.parent / "data" / "sent.json"

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def load_sent() -> dict:
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SENT_FILE.exists():
        return json.loads(SENT_FILE.read_text(encoding="utf-8"))
    return {}

def save_sent(data: dict) -> None:
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def entry(table: dict, key: str) -> dict:
    raw = table.get(key, 0)
    if isinstance(raw, dict):
        return {"name": raw.get("name") or key, "total": float(raw.get("total") or 0)}
    return {"name": key, "total": float(raw or 0)}

class SetupSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Autorole", value="autorole", description="Role given on join"),
            discord.SelectOption(label="Logging", value="logs", description="Log channels"),
            discord.SelectOption(label="Verification", value="verify", description="18+ and creator roles"),
            discord.SelectOption(label="Personal Server", value="personal", description="Private server only settings"),
        ]
        super().__init__(placeholder="What do you want to set up?", options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "autorole":
            await interaction.response.send_modal(AutoroleModal())
        elif choice == "logs":
            await interaction.response.send_modal(LogsModal())
        elif choice == "verify":
            await interaction.response.send_modal(VerifyModal())
        elif choice == "personal":
            await interaction.response.send_modal(PersonalServerModal())

class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(SetupSelect())

class AutoroleModal(discord.ui.Modal, title="Autorole Setup"):
    role_id = discord.ui.TextInput(label="Role ID", placeholder="123456789012345678", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        data[guild]["autorole"] = int(self.role_id.value.strip())
        save(data)
        await interaction.response.send_message("Autorole set.", ephemeral=True)

class LogsModal(discord.ui.Modal, title="Logging Setup"):
    members = discord.ui.TextInput(label="Members log channel ID", placeholder="joins/leaves/roles/bans", required=False)
    messages = discord.ui.TextInput(label="Messages log channel ID", placeholder="deleted/edited", required=False)
    random = discord.ui.TextInput(label="Random log channel ID", placeholder="server/channel/role changes", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        logs = data[guild].setdefault("logs", {})
        if self.members.value.strip():
            logs["members"] = int(self.members.value.strip())
        if self.messages.value.strip():
            logs["messages"] = int(self.messages.value.strip())
        if self.random.value.strip():
            logs["random"] = int(self.random.value.strip())
        save(data)
        await interaction.response.send_message("Logging channels updated.", ephemeral=True)

class VerifyModal(discord.ui.Modal, title="Verification Setup"):
    unverified = discord.ui.TextInput(label="Unverified role ID", required=False)
    verified18 = discord.ui.TextInput(label="18+ role ID", required=False)
    creator = discord.ui.TextInput(label="Creator role ID", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        verify = data[guild].setdefault("verify", {})
        if self.unverified.value.strip():
            verify["unverified"] = int(self.unverified.value.strip())
        if self.verified18.value.strip():
            verify["18"] = int(self.verified18.value.strip())
        if self.creator.value.strip():
            verify["creator"] = int(self.creator.value.strip())
        save(data)
        await interaction.response.send_message("Verification roles updated.", ephemeral=True)

class PersonalServerModal(discord.ui.Modal, title="Personal Server"):
    action = discord.ui.TextInput(
        label="Action",
        placeholder="sent / remove / reset / leaderboard",
        required=True,
    )
    user = discord.ui.TextInput(
        label="User ID (optional)",
        placeholder="123456789012345678",
        required=False,
    )
    name = discord.ui.TextInput(
        label="Name (if not on Discord)",
        placeholder="their name",
        required=False,
    )
    amount = discord.ui.TextInput(
        label="Amount (for sent/remove)",
        placeholder="25.00",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        guild = str(interaction.guild_id)
        data = load_sent()
        table = data.setdefault(guild, {})

        if act == "leaderboard":
            if not table:
                return await interaction.response.send_message("empty.", ephemeral=True)
            rows = []
            for key, raw in table.items():
                item = entry(table, key)
                rows.append((key, item["name"], item["total"]))
            rows.sort(key=lambda r: r[2], reverse=True)
            lines = []
            for i, (key, saved_name, total) in enumerate(rows[:25], start=1):
                if key.isdigit():
                    shown = f"<@{key}>"
                else:
                    shown = saved_name
                lines.append(f"**{i}.** {shown} — ${total:.2f}")
            grand = sum(r[2] for r in rows)
            await interaction.response.send_message(("\n".join(lines) + f"\n\ntotal ${grand:.2f}")[:1900], ephemeral=True)
            return

        if act == "reset":
            data[guild] = {}
            save_sent(data)
            return await interaction.response.send_message("leaderboard wiped.", ephemeral=True)

        if act not in ("sent", "remove"):
            return await interaction.response.send_message("Use: sent / remove / reset / leaderboard", ephemeral=True)

        uid = self.user.value.strip()
        name_val = self.name.value.strip()
        amt_raw = self.amount.value.strip()

        if not uid and not name_val:
            return await interaction.response.send_message("Need a user ID or a name.", ephemeral=True)
        if not amt_raw:
            return await interaction.response.send_message("Need an amount.", ephemeral=True)

        try:
            amount = float(amt_raw)
        except ValueError:
            return await interaction.response.send_message("Amount must be a number.", ephemeral=True)

        key = uid if uid else f"name:{name_val.lower()}"
        label = f"<@{uid}>" if uid else name_val
        display_name = name_val if name_val else uid

        current = entry(table, key)
        if act == "sent":
            total = round(current["total"] + amount, 2)
            table[key] = {"name": display_name, "total": total}
            msg = f"+${amount:.2f} {label} · total ${total:.2f}"
        else:  # remove
            total = round(current["total"] - abs(amount), 2)
            if total <= 0:
                table.pop(key, None)
                total = 0
            else:
                table[key] = {"name": current["name"], "total": total}
            msg = f"-${abs(amount):.2f} {label} · total ${total:.2f}"

        data[guild] = table
        save_sent(data)
        await interaction.response.send_message(msg, ephemeral=True)

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure bot settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_message("Choose what to set up:", view=SetupView(), ephemeral=True)

    @app_commands.command(name="welcomesetup", description="Set up welcome messages")
    @app_commands.describe(
        channel="Channel to send welcomes in",
        line="Text above the embed (use {user}, {name}, {server}, {count})",
        title="Embed title",
        body="Embed description",
        image="Thumbnail image URL (optional)",
        banner="Banner image URL (optional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomesetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        line: str = "hi there {user}! 💎",
        title: str = "welcome to {server}",
        body: str = "you made it.",
        image: str | None = None,
        banner: str | None = None,
    ):
        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        welcome = data[guild].setdefault("welcome", {})

        welcome["channel_id"] = channel.id
        welcome["line"] = line[:200]
        welcome["title"] = title[:256]
        welcome["body"] = body[:4000]
        if image:
            welcome["image"] = image.strip()
        if banner:
            welcome["banner"] = banner.strip()

        save(data)

        await interaction.response.send_message(
            f"Welcome set for {channel.mention}. Use /welcometest to preview.",
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(Setup(bot))