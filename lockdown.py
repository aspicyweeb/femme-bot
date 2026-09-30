import discord
from discord import app_commands
from discord.ext import commands


def everyone(guild: discord.Guild) -> discord.Role:
    return guild.default_role


class Lockdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hide", description="Hide from all members except Administrator staff/bots")
    @app_commands.describe(channel="Defaults to this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def hide(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Pick a text channel.", ephemeral=True)
            return
        guild = interaction.guild
        try:
            await channel.set_permissions(guild.me, view_channel=True, send_messages=True, reason="hide: keep bot")
            for role in guild.roles:
                if role.is_default() or not role.permissions.administrator:
                    await channel.set_permissions(role, view_channel=False, reason=f"hide by {interaction.user}")
                else:
                    await channel.set_permissions(role, view_channel=True, reason=f"hide by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("Bot needs Manage Channel and a role above the ones it edits.", ephemeral=True)
            return
        await interaction.followup.send(f"Hidden {channel.mention} from everyone except Administrator.", ephemeral=True)

    @app_commands.command(name="unhide", description="Restore normal visibility")
    @app_commands.describe(channel="Defaults to this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unhide(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Pick a text channel.", ephemeral=True)
            return
        try:
            for role in interaction.guild.roles:
                overwrite = channel.overwrites_for(role)
                if overwrite.view_channel is not None:
                    overwrite.view_channel = None
                    await channel.set_permissions(role, overwrite=overwrite, reason=f"unhide by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("Bot needs Manage Channel here.", ephemeral=True)
            return
        await interaction.followup.send(f"Unhidden {channel.mention}", ephemeral=True)

    @app_commands.command(name="lock", description="No one can talk. Channel stays visible.")
    @app_commands.describe(channel="Defaults to this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        try:
            await channel.set_permissions(everyone(interaction.guild), send_messages=False, reason=f"lock by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot needs Manage Channel here.", ephemeral=True)
            return
        await interaction.response.send_message(f"Locked {channel.mention}", ephemeral=True)

    @app_commands.command(name="unlock", description="Allow talking again")
    @app_commands.describe(channel="Defaults to this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        try:
            await channel.set_permissions(everyone(interaction.guild), send_messages=None, reason=f"unlock by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("Bot needs Manage Channel here.", ephemeral=True)
            return
        await interaction.response.send_message(f"Unlocked {channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lockdown(bot))
