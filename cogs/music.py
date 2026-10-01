"""
Drop-in music cog for femme bot.

Members: join voice, paste a song name / YouTube link / Spotify track link
in #song-requests. No command needed.

You: /panel or f!panel posts the purple player in the current channel.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands
from yt_dlp import YoutubeDL

PURPLE = 0xB794F6
SPOTIFY_URL = re.compile(
    r"(?:https?://open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(track|playlist|album)/([A-Za-z0-9]+)",
    re.I,
)
YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}


@dataclass
class Track:
    title: str
    stream: str
    page: str
    duration: int | None
    thumbnail: str | None
    requester: str


@dataclass
class GuildPlayer:
    queue: deque[Track] = field(default_factory=deque)
    history: deque[Track] = field(default_factory=deque)
    now: Track | None = None
    volume: float = 0.6
    loop: bool = False
    paused: bool = False
    started_at: float = 0.0
    seek: int = 0
    ignore_after: int = 0
    panel_channel_id: int | None = None
    panel_message_id: int | None = None
    favorites: dict[int, list[str]] = field(default_factory=dict)


def _fmt(seconds: int | None) -> str:
    if not seconds:
        return "?:??"
    minutes, secs = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _http_json(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "femme-bot/1.0", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _spotify_title(url: str) -> str:
    data = _http_json("https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe=""))
    title = (data.get("title") or "").strip()
    author = (data.get("author_name") or "").strip()
    if not title:
        raise RuntimeError("spotify title not found")
    if author and author.lower() not in title.lower():
        return f"{title} {author}"
    return title


class PlayerView(discord.ui.View):
    def __init__(self, cog: "Music") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    async def _go(self, interaction: discord.Interaction, fn) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("server only", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
            await interaction.response.send_message("join a voice channel first", ephemeral=True)
            return
        await fn(interaction)

    @discord.ui.button(label="Previous", emoji="⏮️", style=discord.ButtonStyle.secondary, row=0, custom_id="femme:prev")
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_previous)

    @discord.ui.button(label="Rewind", emoji="⏪", style=discord.ButtonStyle.secondary, row=0, custom_id="femme:rw")
    async def rewind(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, lambda i: self.cog.ui_seek(i, -10))

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.secondary, row=0, custom_id="femme:pause")
    async def pause(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_pause)

    @discord.ui.button(label="Forward", emoji="⏩", style=discord.ButtonStyle.secondary, row=1, custom_id="femme:fw")
    async def forward(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, lambda i: self.cog.ui_seek(i, 10))

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.secondary, row=1, custom_id="femme:skip")
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_skip)

    @discord.ui.button(label="Volume -", emoji="🔉", style=discord.ButtonStyle.secondary, row=2, custom_id="femme:voldn")
    async def vol_down(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, lambda i: self.cog.ui_volume(i, -10))

    @discord.ui.button(label="Loop", emoji="🔁", style=discord.ButtonStyle.secondary, row=2, custom_id="femme:loop")
    async def loop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_loop)

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.secondary, row=2, custom_id="femme:stop")
    async def stop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_stop)

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, row=3, custom_id="femme:shuffle")
    async def shuffle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_shuffle)

    @discord.ui.button(label="Volume +", emoji="🔊", style=discord.ButtonStyle.secondary, row=3, custom_id="femme:volup")
    async def vol_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, lambda i: self.cog.ui_volume(i, 10))

    @discord.ui.button(label="Add To Favourites", emoji="💗", style=discord.ButtonStyle.success, row=4, custom_id="femme:fav")
    async def fav(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._go(interaction, self.cog.ui_favorite)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}
        self.ytdl = YoutubeDL(YTDL_OPTS)
        self.bot.add_view(PlayerView(self))

    def player(self, guild_id: int) -> GuildPlayer:
        return self.players.setdefault(guild_id, GuildPlayer())

    def request_channel(self, channel: discord.abc.GuildChannel) -> bool:
        if not isinstance(channel, discord.TextChannel) or channel.guild is None:
            return False
        state = self.player(channel.guild.id)
        if state.panel_channel_id == channel.id:
            return True
        name = channel.name.lower().replace(" ", "").replace("•", "").replace("-", "").replace("|", "")
        return "song" in name and "request" in name

    def embed(self, state: GuildPlayer) -> discord.Embed:
        if state.now is None:
            card = discord.Embed(
                title="Music Player",
                description=(
                    "No music is currently playing...\n"
                    "Join a voice channel and send a song name or link to start playing."
                ),
                color=PURPLE,
            )
        else:
            track = state.now
            pos = state.seek if state.paused else state.seek + int(max(0, time.time() - state.started_at))
            width = 16
            total = track.duration or 0
            filled = int(width * min(1.0, pos / total)) if total else 0
            bar = "━" * filled + "♡" + "─" * max(0, width - filled - 1)
            card = discord.Embed(
                title="Music Player",
                description=(
                    f"**{track.title}**\n"
                    f"{bar}\n"
                    f"`{_fmt(pos)} / {_fmt(track.duration)}`\n"
                    f"{'paused' if state.paused else 'playing'} · vol {int(state.volume * 100)}% · loop {'on' if state.loop else 'off'}\n"
                    f"requested by {track.requester}"
                ),
                color=PURPLE,
            )
            if track.thumbnail:
                card.set_image(url=track.thumbnail)
        if state.queue:
            lines = [f"`{i}.` {item.title}" for i, item in enumerate(list(state.queue)[:5], start=1)]
            if len(state.queue) > 5:
                lines.append(f"+{len(state.queue) - 5} more")
            card.add_field(name="Up next", value="\n".join(lines), inline=False)
        card.set_footer(text="2D LOBOTOMY · send a song name, youtube link, or spotify link")
        return card

    async def refresh(self, guild: discord.Guild) -> discord.Message | None:
        state = self.player(guild.id)
        if state.panel_channel_id is None:
            return None
        channel = guild.get_channel(state.panel_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None
        view = PlayerView(self)
        card = self.embed(state)
        if state.panel_message_id:
            try:
                msg = await channel.fetch_message(state.panel_message_id)
                await msg.edit(embed=card, view=view)
                return msg
            except discord.NotFound:
                state.panel_message_id = None
        msg = await channel.send(embed=card, view=view)
        state.panel_message_id = msg.id
        return msg

    def queries(self, raw: str) -> list[str]:
        text = raw.strip()
        match = SPOTIFY_URL.search(text)
        if not match:
            return [text]
        kind, spotify_id = match.group(1).lower(), match.group(2)
        if kind != "track":
            raise RuntimeError("paste a spotify track link, or a youtube link / song name")
        return [f"ytsearch1:{_spotify_title(text)} audio"]

    async def extract(self, query: str) -> Track:
        def work():
            data = self.ytdl.extract_info(query, download=False)
            if not data:
                raise RuntimeError("no result")
            if "entries" in data:
                entries = [row for row in data["entries"] if row]
                if not entries:
                    raise RuntimeError("no result")
                data = entries[0]
            thumbs = data.get("thumbnails") or []
            thumb = data.get("thumbnail") or (thumbs[-1].get("url") if thumbs else None)
            return Track(
                title=data.get("title") or "unknown",
                stream=data["url"],
                page=data.get("webpage_url") or query,
                duration=data.get("duration"),
                thumbnail=thumb,
                requester="unknown",
            )

        return await asyncio.to_thread(work)

    async def connect(self, member: discord.Member) -> discord.VoiceClient:
        if member.voice is None or member.voice.channel is None:
            raise commands.CommandError("join a voice channel first")
        channel = member.voice.channel
        vc = member.guild.voice_client
        if vc is None:
            return await channel.connect()
        if vc.channel != channel:
            await vc.move_to(channel)
        return vc

    def source(self, track: Track, state: GuildPlayer) -> discord.AudioSource:
        before = f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {state.seek}"
        audio = discord.FFmpegPCMAudio(track.stream, before_options=before, options="-vn")
        return discord.PCMVolumeTransformer(audio, volume=state.volume)

    def after(self, guild: discord.Guild, err: Exception | None) -> None:
        if err:
            print(f"player error {guild.id}: {err}")
        state = self.player(guild.id)
        if state.ignore_after > 0:
            state.ignore_after -= 1
            return
        asyncio.run_coroutine_threadsafe(self.advance(guild, finished=True), self.bot.loop)

    async def play_now(self, guild: discord.Guild) -> None:
        state = self.player(guild.id)
        vc = guild.voice_client
        if vc is None or state.now is None:
            return
        state.paused = False
        state.started_at = time.time()
        if vc.is_playing() or vc.is_paused():
            state.ignore_after += 1
            vc.stop()
            await asyncio.sleep(0.2)
        try:
            vc.play(self.source(state.now, state), after=lambda e, g=guild: self.after(g, e))
        except discord.ClientException:
            pass

    async def advance(self, guild: discord.Guild, finished: bool = False) -> None:
        state = self.player(guild.id)
        if guild.voice_client is None:
            state.now = None
            await self.refresh(guild)
            return
        if finished and state.loop and state.now is not None:
            state.seek = 0
            await self.play_now(guild)
            await self.refresh(guild)
            return
        if finished and state.now is not None:
            state.history.append(state.now)
        if not state.queue:
            state.now = None
            await self.refresh(guild)
            return
        state.now = state.queue.popleft()
        state.seek = 0
        await self.play_now(guild)
        await self.refresh(guild)

    async def enqueue(self, member: discord.Member, query: str) -> list[Track]:
        searches = await asyncio.to_thread(self.queries, query)
        await self.connect(member)
        state = self.player(member.guild.id)
        loaded: list[Track] = []
        for search in searches:
            track = await self.extract(search)
            track.requester = member.display_name
            state.queue.append(track)
            loaded.append(track)
        vc = member.guild.voice_client
        if vc and not vc.is_playing() and not vc.is_paused() and state.now is None:
            await self.advance(member.guild)
        else:
            await self.refresh(member.guild)
        return loaded

    async def post_panel(self, channel: discord.TextChannel) -> discord.Message:
        state = self.player(channel.guild.id)
        state.panel_channel_id = channel.id
        state.panel_message_id = None
        msg = await self.refresh(channel.guild)
        if msg is None:
            raise RuntimeError("panel failed to send")
        return msg

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if self.request_channel(channel):
                    state = self.player(guild.id)
                    if state.panel_channel_id is None:
                        state.panel_channel_id = channel.id
                    try:
                        await self.refresh(guild)
                    except discord.Forbidden:
                        print(f"cannot post panel in {channel.id}")
                    break

    @commands.command(name="panel")
    @commands.has_permissions(manage_guild=True)
    async def panel_prefix(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        try:
            await self.post_panel(ctx.channel)
        except discord.Forbidden:
            await ctx.reply("can't post here even with admin. check the bot role is above channel overwrites.")
            return
        await ctx.reply("player posted. members can drop a link in this channel.", delete_after=8)

    @app_commands.command(name="panel", description="Post the music player in this channel")
    @app_commands.default_permissions(manage_guild=True)
    async def panel_slash(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("text channel only", ephemeral=True)
            return
        try:
            await self.post_panel(interaction.channel)
        except discord.Forbidden:
            await interaction.response.send_message("can't post in this channel", ephemeral=True)
            return
        await interaction.response.send_message("player posted. drop a link to play.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not isinstance(message.channel, discord.TextChannel):
            return
        if not self.request_channel(message.channel):
            return
        query = message.content.strip()
        if not query or query.startswith(("f!", "/", "!", ".")):
            return
        if not isinstance(message.author, discord.Member):
            return
        state = self.player(message.guild.id)
        state.panel_channel_id = message.channel.id
        try:
            await self.enqueue(message.author, query)
        except Exception as exc:
            await message.reply(f"couldn't play that: `{exc}`", delete_after=12)
            return
        try:
            await message.add_reaction("💗")
        except discord.HTTPException:
            pass
        await self.refresh(message.guild)

    async def ui_pause(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        vc = guild.voice_client
        state = self.player(guild.id)
        if vc is None or state.now is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        if vc.is_playing():
            state.seek += int(max(0, time.time() - state.started_at))
            state.paused = True
            vc.pause()
        elif vc.is_paused():
            state.started_at = time.time()
            state.paused = False
            vc.resume()
        await interaction.response.edit_message(embed=self.embed(state), view=PlayerView(self))

    async def ui_skip(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        await interaction.response.defer()
        vc.stop()

    async def ui_stop(self, interaction: discord.Interaction) -> None:
        state = self.player(interaction.guild.id)
        state.queue.clear()
        state.now = None
        vc = interaction.guild.voice_client
        if vc:
            state.ignore_after += 1
            vc.stop()
        await interaction.response.edit_message(embed=self.embed(state), view=PlayerView(self))

    async def ui_loop(self, interaction: discord.Interaction) -> None:
        state = self.player(interaction.guild.id)
        state.loop = not state.loop
        await interaction.response.edit_message(embed=self.embed(state), view=PlayerView(self))

    async def ui_shuffle(self, interaction: discord.Interaction) -> None:
        state = self.player(interaction.guild.id)
        items = list(state.queue)
        random.shuffle(items)
        state.queue = deque(items)
        await interaction.response.edit_message(embed=self.embed(state), view=PlayerView(self))

    async def ui_volume(self, interaction: discord.Interaction, delta: int) -> None:
        state = self.player(interaction.guild.id)
        state.volume = min(1.0, max(0.05, state.volume + delta / 100))
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = state.volume
        await interaction.response.edit_message(embed=self.embed(state), view=PlayerView(self))

    async def ui_previous(self, interaction: discord.Interaction) -> None:
        state = self.player(interaction.guild.id)
        if not state.history:
            await interaction.response.send_message("no previous track", ephemeral=True)
            return
        if state.now:
            state.queue.appendleft(state.now)
        state.queue.appendleft(state.history.pop())
        state.now = None
        await interaction.response.defer()
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()

    async def ui_seek(self, interaction: discord.Interaction, delta: int) -> None:
        state = self.player(interaction.guild.id)
        if state.now is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        pos = state.seek if state.paused else state.seek + int(max(0, time.time() - state.started_at))
        pos = max(0, pos + delta)
        if state.now.duration:
            pos = min(pos, max(0, state.now.duration - 1))
        state.seek = pos
        await interaction.response.defer()
        await self.play_now(interaction.guild)
        await self.refresh(interaction.guild)

    async def ui_favorite(self, interaction: discord.Interaction) -> None:
        state = self.player(interaction.guild.id)
        if state.now is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        bag = state.favorites.setdefault(interaction.user.id, [])
        if state.now.page in bag:
            await interaction.response.send_message("already saved", ephemeral=True)
            return
        bag.append(state.now.page)
        await interaction.response.send_message(f"saved **{state.now.title}**", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
    try:
        await bot.tree.sync()
    except Exception as exc:
        print(f"slash sync failed: {exc}")
