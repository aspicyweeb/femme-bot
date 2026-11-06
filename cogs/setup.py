import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"
LEADERBOARD_FILE = Path(__file__).resolve().parent.parent / "data" / "leaderboard.json"

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}

def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def load_lb() -> dict:
    LEADERBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LEADERBOARD_FILE.exists():
        return json.loads(LEADERBOARD_FILE.read_text(encoding="utf-8"))
    return {}

def save_lb(data: dict) -> None:
    LEADERBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEADERBOARD_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

class SetupSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Autorole", value="autorole", description="Role given on join"),
            discord.SelectOption(label="Logging", value="logs", description="Log channels"),
            discord.SelectOption(label="Welcome", value="welcome", description="Welcome messages"),
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
        elif choice == "welcome":
            await interaction.response.send_modal(WelcomeModal())
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

class WelcomeModal(discord.ui.Modal, title="Welcome Setup"):
    channel = discord.ui.TextInput(label="Welcome channel ID", required=True)
    line = discord.ui.TextInput(label="Line", default="hi there {user}! 💎", required=False)
    title = discord.ui.TextInput(label="Title", default="welcome to {server}", required=False)
    body = discord.ui.TextInput(label="Body", style=discord.TextStyle.paragraph, default="you made it.", required=False)
    image = discord.ui.TextInput(label="Thumbnail URL (optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        welcome = data[guild].setdefault("welcome", {})
        welcome["channel_id"] = int(self.channel.value.strip())
        welcome["line"] = self.line.value.strip() or "hi there {user}! 💎"
        welcome["title"] = self.title.value.strip() or "welcome to {server}"
        welcome["body"] = self.body.value.strip() or "you made it."
        if self.image.value.strip():
            welcome["image"] = self.image.value.strip()
        save(data)
        await interaction.response.send_message("Welcome settings saved.", ephemeral=True)

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
        label="User ID (for sent/remove)",
        placeholder="123456789012345678",
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
        data = load_lb()
        data.setdefault(guild, {})

        if act == "leaderboard":
            entries = data[guild]
            if not entries:
                return await interaction.response.send_message("Leaderboard is empty.", ephemeral=True)
            lines = []
            for uid, total in sorted(entries.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"<@{uid}> — ${float(total):.2f}")
            await interaction.response.send_message("\n".join(lines[:20]), ephemeral=True)
            return

        if act == "reset":
            data[guild] = {}
            save_lb(data)
            return await interaction.response.send_message("Leaderboard wiped.", ephemeral=True)

        if act not in ("sent", "remove"):
            return await interaction.response.send_message("Use: sent / remove / reset / leaderboard", ephemeral=True)

        uid = self.user.value.strip()
        amt_raw = self.amount.value.strip()
        if not uid or not amt_raw:
            return await interaction.response.send_message("Need a user ID and amount.", ephemeral=True)

        try:
            amount = float(amt_raw)
        except ValueError:
            return await interaction.response.send_message("Amount must be a number.", ephemeral=True)

        current = float(data[guild].get(uid, 0))
        if act == "sent":
            data[guild][uid] = round(current + amount, 2)
            msg = f"Added ${amount:.2f} to <@{uid}> (now ${data[guild][uid]:.2f})"
        else:  # remove
            data[guild][uid] = round(max(0, current - amount), 2)
            msg = f"Removed ${amount:.2f} from <@{uid}> (now ${data[guild][uid]:.2f})"

        save_lb(data)
        await interaction.response.send_message(msg, ephemeral=True)

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure bot settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_message("Choose what to set up:", view=SetupView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Setup(bot))
