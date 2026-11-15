"""
Poll Cog for Femme Bot - EasyPoll-like + 2DFD Gen of the Day Contest
discord.py 2.x

Features:
- /poll : Create multi-option polls with buttons
- Poll types: public, anonymous, hidden, blind
- Numbers + custom emotes support
- maxchoices, role restriction, timed polls
- /closepoll, /results
- /gencontest, /submitgen, /genleaderboard
- Persistent votes via JSON
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import time
import re
from datetime import datetime, timedelta
from typing import Optional, Literal

DATA_FILE = "polls_data.json"

def parse_option(raw: str):
    """Extract leading custom/unicode emoji and the rest of the option text."""
    raw = raw.strip()
    # Discord custom emoji: <:name:id> or <a:name:id>
    custom = re.match(r'^(<a?:[a-zA-Z0-9_]+:\d+>)\s*(.*)', raw)
    if custom:
        return custom.group(1), custom.group(2) or raw
    # Unicode emoji at the start
    if raw and not raw[0].isalnum() and raw[0] not in "()[]":
        emoji = raw[0]
        text = raw[1:].strip()
        if text:
            return emoji, text
    return None, raw

class PollButton(discord.ui.Button):
    def __init__(self, label: str, poll_id: str, option_index: int, emoji=None, style: discord.ButtonStyle = discord.ButtonStyle.primary):
        custom_id = f"poll_{poll_id}_{option_index}"
        super().__init__(label=label[:80], custom_id=custom_id, style=style, emoji=emoji)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

class PollView(discord.ui.View):
    def __init__(self, poll_id: str, options: list[str], cog):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.options = options
        self.cog = cog
        for i, opt in enumerate(options):
            emoji, text = parse_option(opt)
            label = f"{i+1}. {text}"[:80]
            btn = PollButton(label=label, poll_id=poll_id, option_index=i, emoji=emoji)
            self.add_item(btn)

class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = self.load_data()
        self.bot.loop.create_task(self.restore_views())

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        return {"polls": {}, "contests": {}}

    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    async def restore_views(self):
        await self.bot.wait_until_ready()
        for poll_id, poll in self.data.get("polls", {}).items():
            if not poll.get("closed"):
                options = poll.get("options", [])
                view = PollView(poll_id, options, self)
                self.bot.add_view(view)

    def make_poll_embed(self, poll: dict) -> discord.Embed:
        embed = discord.Embed(color=0x2b2d31)

        embed.add_field(name="Question", value=poll["question"], inline=False)

        choices_lines = []
        for i, opt in enumerate(poll["options"]):
            emoji, text = parse_option(opt)
            prefix = f"{emoji} " if emoji else ""
            choices_lines.append(f"**{i+1}.** {prefix}{text}")
        embed.add_field(name="Choices", value="\n".join(choices_lines), inline=False)

        total_votes = sum(len(v) for v in poll["votes"].values())
        unique_users = len(poll.get("voters", {}))

        show_results = poll.get("closed") or poll["type"] not in ("hidden", "blind")

        if show_results and total_votes > 0:
            result_lines = []
            for i, opt in enumerate(poll["options"]):
                emoji, text = parse_option(opt)
                count = len(poll["votes"].get(str(i), []))
                pct = (count / total_votes * 100) if total_votes else 0
                prefix = f"{emoji} " if emoji else ""
                result_lines.append(f"**{i+1}.** {prefix}{text} — {pct:.1f}% ({count})")
            result_title = "Final Result" if poll.get("closed") else "Results"
            embed.add_field(name=result_title, value="\n".join(result_lines) + f"\n*{total_votes} votes from {unique_users} users*", inline=False)
        elif poll["type"] in ("hidden", "blind") and not poll.get("closed"):
            embed.add_field(name="Results", value="*Hidden until the poll ends*", inline=False)

        settings = []
        if poll.get("end_time"):
            if poll.get("closed") or time.time() > poll["end_time"]:
                settings.append("🕒 Poll already ended")
            else:
                settings.append(f"🕒 Ends <t:{int(poll['end_time'])}:R>")
        type_label = {
            "public": "Public",
            "anonymous": "Anonymous",
            "hidden": "Hidden Results",
            "blind": "Blind Voting"
        }.get(poll["type"], poll["type"].title())
        settings.append(f"🗳️ {type_label}")
        settings.append(f"👥 {poll['maxchoices']} allowed choices")
        if poll.get("closed"):
            settings.append("🔒 No other votes allowed")
        embed.add_field(name="Settings", value="\n".join(settings), inline=False)

        embed.set_footer(text=f"Poll ID: {poll['id']}")
        return embed

    @app_commands.command(name="poll", description="Create a poll (EasyPoll style)")
    @app_commands.describe(
        question="The poll question",
        options="Options separated by | (e.g. Yes | No | Maybe)",
        poll_type="Visibility type",
        maxchoices="How many options a user can pick (default 1)",
        duration="Duration like 1h, 30m, 1d (optional, for timed)",
        allowed_role="Role allowed to vote (optional)"
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        poll_type: Literal["public", "anonymous", "hidden", "blind"] = "public",
        maxchoices: int = 1,
        duration: Optional[str] = None,
        allowed_role: Optional[discord.Role] = None
    ):
        opts = [o.strip() for o in options.split("|") if o.strip()]
        if len(opts) < 2 or len(opts) > 20:
            return await interaction.response.send_message("Need 2-20 options separated by |", ephemeral=True)

        poll_id = str(int(time.time() * 1000))
        end_time = None
        if duration:
            unit = duration[-1].lower()
            try:
                num = int(duration[:-1])
                if unit == "m":
                    end_time = time.time() + num * 60
                elif unit == "h":
                    end_time = time.time() + num * 3600
                elif unit == "d":
                    end_time = time.time() + num * 86400
            except:
                return await interaction.response.send_message("Invalid duration (use 10m, 2h, 1d)", ephemeral=True)

        poll_data = {
            "id": poll_id,
            "question": question,
            "options": opts,
            "type": poll_type,
            "maxchoices": maxchoices,
            "votes": {str(i): [] for i in range(len(opts))},
            "voters": {},
            "channel_id": interaction.channel_id,
            "message_id": None,
            "creator": interaction.user.id,
            "end_time": end_time,
            "closed": False,
            "allowed_role": allowed_role.id if allowed_role else None,
            "created": time.time()
        }
        self.data["polls"][poll_id] = poll_data
        self.save_data()

        embed = self.make_poll_embed(poll_data)
        view = PollView(poll_id, opts, self)

        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        poll_data["message_id"] = msg.id
        self.save_data()

    @app_commands.command(name="closepoll", description="Close a poll")
    @app_commands.describe(poll_id="The poll ID from the footer")
    async def closepoll(self, interaction: discord.Interaction, poll_id: str):
        poll = self.data["polls"].get(poll_id)
        if not poll or poll["closed"]:
            return await interaction.response.send_message("Poll not found or already closed.", ephemeral=True)
        if interaction.user.id != poll["creator"] and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Only the creator or mods can close.", ephemeral=True)

        poll["closed"] = True
        self.save_data()
        embed = self.make_poll_embed(poll)
        await interaction.response.send_message("Poll closed! Final results are now visible.", ephemeral=True)
        try:
            channel = self.bot.get_channel(poll["channel_id"])
            msg = await channel.fetch_message(poll["message_id"])
            await msg.edit(embed=embed, view=None)
        except:
            pass

    @app_commands.command(name="results", description="Show full results of a poll")
    async def results(self, interaction: discord.Interaction, poll_id: str):
        poll = self.data["polls"].get(poll_id)
        if not poll:
            return await interaction.response.send_message("Poll not found.", ephemeral=True)
        embed = self.make_poll_embed(poll)
        if poll["type"] == "public":
            voters_text = []
            for i, opt in enumerate(poll["options"]):
                users = poll["votes"].get(str(i), [])
                if users:
                    mentions = " ".join(f"<@{u}>" for u in users[:5])
                    voters_text.append(f"**{opt}**: {mentions}{'...' if len(users)>5 else ''}")
            if voters_text:
                embed.add_field(name="Voters (public)", value="\n".join(voters_text)[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gencontest", description="Start a 2DFD Gen of the Day contest")
    @app_commands.describe(
        title="Contest title (e.g. Best Bubbles Gen Today)",
        duration="How long submissions/voting last (e.g. 1d)",
        max_submissions="Max gens per user"
    )
    async def gencontest(
        self,
        interaction: discord.Interaction,
        title: str,
        duration: str = "1d",
        max_submissions: int = 3
    ):
        contest_id = str(int(time.time() * 1000))
        end_time = time.time() + 86400
        unit = duration[-1].lower()
        try:
            num = int(duration[:-1])
            if unit == "h":
                end_time = time.time() + num * 3600
            elif unit == "d":
                end_time = time.time() + num * 86400
        except:
            pass

        self.data["contests"][contest_id] = {
            "id": contest_id,
            "title": title,
            "submissions": {},
            "end_time": end_time,
            "max_per_user": max_submissions,
            "channel_id": interaction.channel_id,
            "active": True,
            "creator": interaction.user.id
        }
        self.save_data()

        embed = discord.Embed(
            title=f"✨ 2DFD Gen of the Day: {title}",
            description=f"Submit your gens with `/submitgen` !\nEnds: <t:{int(end_time)}:R>",
            color=0xff69b4
        )
        embed.set_footer(text=f"Contest ID: {contest_id}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="submitgen", description="Submit a gen for the active contest")
    @app_commands.describe(
        contest_id="Contest ID",
        image="The image of your gen",
        caption="Optional caption / prompt used"
    )
    async def submitgen(
        self,
        interaction: discord.Interaction,
        contest_id: str,
        image: discord.Attachment,
        caption: Optional[str] = None
    ):
        contest = self.data["contests"].get(contest_id)
        if not contest or not contest["active"]:
            return await interaction.response.send_message("No active contest with that ID.", ephemeral=True)
        if time.time() > contest["end_time"]:
            return await interaction.response.send_message("Contest ended.", ephemeral=True)

        user_subs = contest["submissions"].get(str(interaction.user.id), [])
        if len(user_subs) >= contest["max_per_user"]:
            return await interaction.response.send_message(f"Max {contest['max_per_user']} submissions reached.", ephemeral=True)

        embed = discord.Embed(
            title=f"Gen by {interaction.user.display_name}",
            description=caption or "No caption",
            color=0xffb6c1
        )
        embed.set_image(url=image.url)
        embed.set_footer(text=f"Contest: {contest_id} | Votes: 0")

        view = discord.ui.View(timeout=None)
        vote_btn = discord.ui.Button(label="Vote 💖", custom_id=f"genvote_{contest_id}_{interaction.user.id}_{len(user_subs)}", style=discord.ButtonStyle.success)
        view.add_item(vote_btn)

        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()

        sub = {
            "image_url": image.url,
            "caption": caption,
            "message_id": msg.id,
            "votes": [],
            "submitter": interaction.user.id
        }
        if str(interaction.user.id) not in contest["submissions"]:
            contest["submissions"][str(interaction.user.id)] = []
        contest["submissions"][str(interaction.user.id)].append(sub)
        self.save_data()

    @app_commands.command(name="genleaderboard", description="Show the current Gen of the Day leaderboard")
    @app_commands.describe(contest_id="Contest ID")
    async def genleaderboard(self, interaction: discord.Interaction, contest_id: str):
        contest = self.data["contests"].get(contest_id)
        if not contest:
            return await interaction.response.send_message("Contest not found.", ephemeral=True)

        all_subs = []
        for user_id, subs in contest["submissions"].items():
            for sub in subs:
                all_subs.append({
                    "votes": len(sub["votes"]),
                    "submitter": int(user_id),
                    "caption": sub.get("caption") or "No caption",
                    "image": sub["image_url"]
                })

        all_subs.sort(key=lambda x: x["votes"], reverse=True)

        embed = discord.Embed(
            title=f"🏆 {contest['title']} Leaderboard",
            color=0xff69b4
        )
        if not all_subs:
            embed.description = "No submissions yet."
        else:
            lines = []
            for i, sub in enumerate(all_subs[:10], 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                lines.append(f"{medal} <@{sub['submitter']}> — **{sub['votes']}** votes\n> {sub['caption'][:50]}")
            embed.description = "\n".join(lines)
        embed.set_footer(text=f"Contest ID: {contest_id}")
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("poll_"):
            await self.handle_poll_vote(interaction, custom_id)
        elif custom_id.startswith("genvote_"):
            await self.handle_gen_vote(interaction, custom_id)

    async def handle_poll_vote(self, interaction: discord.Interaction, custom_id: str):
        parts = custom_id.split("_")
        if len(parts) < 3:
            return
        poll_id = parts[1]
        opt_index = parts[2]
        poll = self.data["polls"].get(poll_id)
        if not poll or poll["closed"]:
            return await interaction.response.send_message("Poll closed or invalid.", ephemeral=True)

        if poll["allowed_role"]:
            role = interaction.guild.get_role(poll["allowed_role"])
            if role not in interaction.user.roles:
                return await interaction.response.send_message("You don't have the required role to vote.", ephemeral=True)

        user_id = str(interaction.user.id)
        voters = poll.setdefault("voters", {})
        user_votes = voters.get(user_id, [])

        if opt_index in user_votes:
            user_votes.remove(opt_index)
            if interaction.user.id in poll["votes"].get(opt_index, []):
                poll["votes"][opt_index].remove(interaction.user.id)
            action = "removed"
        else:
            if len(user_votes) >= poll["maxchoices"]:
                return await interaction.response.send_message(f"Max {poll['maxchoices']} choices.", ephemeral=True)
            user_votes.append(opt_index)
            poll["votes"].setdefault(opt_index, []).append(interaction.user.id)
            action = "added"

        voters[user_id] = user_votes
        self.save_data()

        embed = self.make_poll_embed(poll)
        try:
            await interaction.response.edit_message(embed=embed)
        except:
            await interaction.response.send_message(f"Vote {action}!", ephemeral=True)
            try:
                channel = self.bot.get_channel(poll["channel_id"])
                msg = await channel.fetch_message(poll["message_id"])
                await msg.edit(embed=embed)
            except:
                pass

    async def handle_gen_vote(self, interaction: discord.Interaction, custom_id: str):
        parts = custom_id.split("_")
        if len(parts) < 4:
            return await interaction.response.send_message("Invalid vote button.", ephemeral=True)
        
        contest_id = parts[1]
        submitter_id = parts[2]
        try:
            sub_index = int(parts[3])
        except:
            return await interaction.response.send_message("Invalid submission.", ephemeral=True)

        contest = self.data["contests"].get(contest_id)
        if not contest or not contest.get("active"):
            return await interaction.response.send_message("Contest not found or closed.", ephemeral=True)

        user_subs = contest["submissions"].get(submitter_id, [])
        if sub_index >= len(user_subs):
            return await interaction.response.send_message("Submission not found.", ephemeral=True)

        sub = user_subs[sub_index]
        voter_id = interaction.user.id

        if voter_id in sub["votes"]:
            sub["votes"].remove(voter_id)
            action = "removed your vote from"
        else:
            sub["votes"].append(voter_id)
            action = "voted for"

        self.save_data()

        try:
            channel = self.bot.get_channel(contest["channel_id"])
            msg = await channel.fetch_message(sub["message_id"])
            embed = msg.embeds[0]
            embed.set_footer(text=f"Contest: {contest_id} | Votes: {len(sub['votes'])}")
            await msg.edit(embed=embed)
        except Exception:
            pass

        await interaction.response.send_message(f"Successfully {action} this gen! Total votes: {len(sub['votes'])}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Polls(bot))