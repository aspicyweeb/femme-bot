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
