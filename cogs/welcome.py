class WelcomeModal(discord.ui.Modal, title="Welcome Setup"):
    channel = discord.ui.TextInput(
        label="Welcome channel",
        placeholder="#general or channel ID",
        required=True,
    )
    line = discord.ui.TextInput(label="Line", default="hi there {user}! 💎", required=False)
    title = discord.ui.TextInput(label="Title", default="welcome to {server}", required=False)
    body = discord.ui.TextInput(label="Body", style=discord.TextStyle.paragraph, default="you made it.", required=False)
    image = discord.ui.TextInput(label="Thumbnail URL (optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.channel.value.strip()

        # Handle <#123456789> mention or raw ID
        if raw.startswith("<#") and raw.endswith(">"):
            channel_id_str = raw[2:-1]
        else:
            channel_id_str = raw

        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return await interaction.response.send_message(
                "Use a channel mention (#channel) or the channel ID.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "That channel is invalid or not a text channel.",
                ephemeral=True,
            )

        data = load()
        guild = str(interaction.guild_id)
        data.setdefault(guild, {})
        welcome = data[guild].setdefault("welcome", {})
        welcome["channel_id"] = channel_id
        welcome["line"] = self.line.value.strip() or "hi there {user}! 💎"
        welcome["title"] = self.title.value.strip() or "welcome to {server}"
        welcome["body"] = self.body.value.strip() or "you made it."
        if self.image.value.strip():
            welcome["image"] = self.image.value.strip()
        save(data)

        await interaction.response.send_message(
            f"Welcome set for {channel.mention}. Use /welcometest to preview.",
            ephemeral=True,
        )