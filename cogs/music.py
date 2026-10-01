from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import deque
from dataclasses import dataclass, field

import discord
from discord.ext import commands
from yt_dlp import YoutubeDL

SPOTIFY_URL = re.compile(
    r"(https?://open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(track|playlist|album|artist)/([A-Za-z0-9]+)",
    re.I,
)


def _http_json(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "femme-bot/1.0", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _spotify_oembed_title(url: str) -> str:
    endpoint = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe="")
    data = _http_json(endpoint)
    title = (data.get("title") or "").strip()
    author = (data.get("author_name") or "").strip()
    if author and author.lower() not in title.lower():
        return f"{title} {author}"
    if title:
        return title
    raise RuntimeError("spotify title not found")


_spotify_token: dict = {"access_token": None, "expires": 0}


def _spotify_token_get() -> str | None:
    cid = os.environ.get("SPOTIFY_CLIENT_ID")
    secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not cid or not secret:
        return None
    if _spotify_token["access_token"] and _spotify_token["expires"] > time.time() + 30:
        return _spotify_token["access_token"]
    basic = urllib.parse.quote(cid) + ":" + urllib.parse.quote(secret)
    import base64

    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    payload = _http_json(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        data=data,
    )
    _spotify_token["access_token"] = payload["access_token"]
    _spotify_token["expires"] = time.time() + int(payload.get("expires_in", 3600))
    return _spotify_token["access_token"]


def _spotify_api(path: str) -> dict:
    token = _spotify_token_get()
    if not token:
        raise RuntimeError("set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET for playlists/albums")
    return _http_json(
        "https://api.spotify.com/v1/" + path.lstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
    )


def _track_query(track: dict) -> str:
    name = track.get("name") or ""
    artists = ", ".join(a.get("name", "") for a in track.get("artists") or [])
    return f"{name} {artists}".strip()


PINK = 0xB794F6
PANEL_IMAGE = "https://media.discordapp.net/attachments/0/diva-placeholder.png"

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
    url: str
    webpage_url: str
    duration: int | None
    thumbnail: str | None
    requester_id: int
    requester_name: str


@dataclass
class GuildPlayer:
    guild_id: int
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
    m, s = divmod(max(0, int(seconds)), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _elapsed(player: GuildPlayer) -> int:
    if player.now is None:
        return 0
    if player.paused:
        return player.seek
    return player.seek + int(max(0, time.time() - player.started_at))


class PlayerView(discord.ui.View):
    def __init__(self, cog: "Music") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    async def _act(self, interaction: discord.Interaction, fn) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("guild only", ephemeral=True)
            return
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.response.send_message("join a voice channel first", ephemeral=True)
            return
        await fn(interaction)

    @discord.ui.button(label="Previous", emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_previous)

    @discord.ui.button(label="Rewind", emoji="⏪", style=discord.ButtonStyle.secondary, row=0)
    async def rewind(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, lambda i: self.cog.ui_seek(i, -10))

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.secondary, row=0, custom_id="femme:pause")
    async def pause(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_pause)

    @discord.ui.button(label="Forward", emoji="⏩", style=discord.ButtonStyle.secondary, row=1)
    async def forward(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, lambda i: self.cog.ui_seek(i, 10))

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.secondary, row=1)
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_skip)

    @discord.ui.button(label="Volume -", emoji="🔉", style=discord.ButtonStyle.secondary, row=2)
    async def vol_down(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, lambda i: self.cog.ui_volume(i, -10))

    @discord.ui.button(label="Loop", emoji="🔁", style=discord.ButtonStyle.secondary, row=2)
    async def loop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_loop)

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.secondary, row=2)
    async def stop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_stop)

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, row=3)
    async def shuffle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_shuffle)

    @discord.ui.button(label="Volume +", emoji="🔊", style=discord.ButtonStyle.secondary, row=3)
    async def vol_up(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, lambda i: self.cog.ui_volume(i, 10))

    @discord.ui.button(label="Add To Favourites", emoji="💗", style=discord.ButtonStyle.success, row=4)
    async def fav(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._act(interaction, self.cog.ui_favorite)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        if not hasattr(bot, "music_players"):
            bot.music_players = {}
        self.ytdl = YoutubeDL(YTDL_OPTS)
        self.bot.add_view(PlayerView(self))

    def _player(self, guild_id: int) -> GuildPlayer:
        players: dict[int, GuildPlayer] = self.bot.music_players
        if guild_id not in players:
            players[guild_id] = GuildPlayer(guild_id=guild_id)
        return players[guild_id]

    def _is_request_channel(self, channel: discord.abc.Messageable) -> bool:
        if not isinstance(channel, discord.TextChannel):
            return False
        name = channel.name.lower().replace(" ", "")
        return "song" in name and "request" in name

    def build_embed(self, player: GuildPlayer) -> discord.Embed:
        if player.now is None:
            embed = discord.Embed(
                title="Music Player",
                description=(
                    "No music is currently playing...\n"
                    "Join a voice channel and send a song name or link to start playing."
                ),
                color=PINK,
            )
        else:
            t = player.now
            pos = _elapsed(player)
            bar = self._bar(pos, t.duration or 0)
            loop = "on" if player.loop else "off"
            state = "paused" if player.paused else "playing"
            embed = discord.Embed(
                title="Music Player",
                description=(
                    f"**{t.title}**\n"
                    f"{bar}\n"
                    f"`{_fmt(pos)} / {_fmt(t.duration)}`\n"
                    f"{state} · vol {int(player.volume * 100)}% · loop {loop}\n"
                    f"requested by {t.requester_name}"
                ),
                color=PINK,
            )
        if player.queue:
            preview = "\n".join(
                f"`{i}.` {track.title}" for i, track in enumerate(list(player.queue)[:5], start=1)
            )
            extra = f"\n+{len(player.queue) - 5} more" if len(player.queue) > 5 else ""
            embed.add_field(name="Up next", value=preview + extra, inline=False)
        art = player.now.thumbnail if player.now and player.now.thumbnail else None
        if art:
            embed.set_image(url=art)
        embed.set_footer(text="2D LOBOTOMY · send a song name, youtube link, or spotify link")
        return embed

    @staticmethod
    def _bar(pos: int, total: int, width: int = 16) -> str:
        if total <= 0:
            return "♡" + "—" * (width - 1)
        filled = int(width * min(1.0, pos / total))
        return "━" * filled + "♡" + "─" * max(0, width - filled - 1)

    async def refresh_panel(self, guild: discord.Guild) -> None:
        player = self._player(guild.id)
        if player.panel_channel_id is None:
            return
        channel = guild.get_channel(player.panel_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.build_embed(player)
        view = PlayerView(self)
        if player.panel_message_id:
            try:
                msg = await channel.fetch_message(player.panel_message_id)
                await msg.edit(embed=embed, view=view)
                return
            except discord.NotFound:
                player.panel_message_id = None
        msg = await channel.send(embed=embed, view=view)
        player.panel_message_id = msg.id

    def _normalize_query(self, query: str) -> list[str]:
        raw = query.strip()
        match = SPOTIFY_URL.search(raw)
        if not match:
            return [raw]
        kind = match.group(2).lower()
        spotify_id = match.group(3)
        if kind == "track":
            try:
                data = _spotify_api(f"tracks/{spotify_id}")
                return [f"ytsearch1:{_track_query(data)} audio"]
            except Exception:
                return [f"ytsearch1:{_spotify_oembed_title(raw)} audio"]
        if kind == "artist":
            raise RuntimeError("paste a track, album, or playlist link — not an artist page")
        if kind == "album":
            data = _spotify_api(f"albums/{spotify_id}/tracks?limit=50")
            queries = [f"ytsearch1:{_track_query(item)} audio" for item in data.get("items") or [] if item]
            if not queries:
                raise RuntimeError("empty album")
            return queries
        # playlist
        items: list[dict] = []
        path = f"playlists/{spotify_id}/tracks?limit=50"
        while path and len(items) < 50:
            page = _spotify_api(path.replace("https://api.spotify.com/v1/", ""))
            for row in page.get("items") or []:
                track = row.get("track") or {}
                if track and track.get("name"):
                    items.append(track)
            nxt = page.get("next")
            path = nxt.replace("https://api.spotify.com/v1/", "") if nxt else ""
        queries = [f"ytsearch1:{_track_query(t)} audio" for t in items]
        if not queries:
            raise RuntimeError("empty or private playlist")
        return queries[:50]

    async def _extract(self, query: str) -> Track:
        def work():
            data = self.ytdl.extract_info(query, download=False)
            if data is None:
                raise RuntimeError("no result")
            if "entries" in data:
                entries = [e for e in data["entries"] if e]
                if not entries:
                    raise RuntimeError("no result")
                data = entries[0]
            return data

        data = await asyncio.to_thread(work)
        thumb = None
        thumbs = data.get("thumbnails") or []
        if thumbs:
            thumb = thumbs[-1].get("url")
        return Track(
            title=data.get("title") or "unknown",
            url=data["url"],
            webpage_url=data.get("webpage_url") or query,
            duration=data.get("duration"),
            thumbnail=data.get("thumbnail") or thumb,
            requester_id=0,
            requester_name="unknown",
        )

    async def _ensure_voice(self, member: discord.Member, guild: discord.Guild) -> discord.VoiceClient:
        if member.voice is None or member.voice.channel is None:
            raise commands.CommandError("join a voice channel first")
        channel = member.voice.channel
        vc = guild.voice_client
        if vc is None:
            return await channel.connect()
        if vc.channel != channel:
            await vc.move_to(channel)
        return vc

    def _ffmpeg(self, track: Track, player: GuildPlayer) -> discord.AudioSource:
        before = f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {player.seek}"
        source = discord.FFmpegPCMAudio(track.url, before_options=before, options="-vn")
        return discord.PCMVolumeTransformer(source, volume=player.volume)

    def _after(self, guild: discord.Guild, err: Exception | None) -> None:
        if err:
            print(f"player error {guild.id}: {err}")
        player = self._player(guild.id)
        if player.ignore_after > 0:
            player.ignore_after -= 1
            return
        asyncio.run_coroutine_threadsafe(self._advance(guild, from_end=True), self.bot.loop)

    async def _start_now(self, guild: discord.Guild, track: Track, seek: int = 0) -> None:
        player = self._player(guild.id)
        vc = guild.voice_client
        if vc is None:
            return
        player.now = track
        player.seek = max(0, seek)
        player.paused = False
        player.started_at = time.time()
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        # stop() triggers after(); guard by setting a skip flag via seek restart
        vc.play(self._ffmpeg(track, player), after=lambda e, g=guild: self._after(g, e))

    async def _advance(self, guild: discord.Guild, from_end: bool = False) -> None:
        player = self._player(guild.id)
        vc = guild.voice_client
        if vc is None:
            player.now = None
            await self.refresh_panel(guild)
            return
        if from_end and player.loop and player.now is not None:
            await self._play_current(guild)
            await self.refresh_panel(guild)
            return
        if from_end and player.now is not None:
            player.history.append(player.now)
            if len(player.history) > 50:
                player.history.popleft()
        if not player.queue:
            player.now = None
            await self.refresh_panel(guild)
            return
        track = player.queue.popleft()
        player.now = track
        player.seek = 0
        await self._play_current(guild)
        await self.refresh_panel(guild)

    async def _play_current(self, guild: discord.Guild) -> None:
        player = self._player(guild.id)
        vc = guild.voice_client
        if vc is None or player.now is None:
            return
        player.paused = False
        player.started_at = time.time()
        if vc.is_playing() or vc.is_paused():
            player.ignore_after += 1
            try:
                vc.stop()
            except Exception:
                player.ignore_after = max(0, player.ignore_after - 1)
            await asyncio.sleep(0.15)
        try:
            vc.play(self._ffmpeg(player.now, player), after=lambda e, g=guild: self._after(g, e))
        except discord.ClientException:
            # already playing after stop race
            pass

    async def enqueue(self, member: discord.Member, query: str) -> list[Track]:
        searches = await asyncio.to_thread(self._normalize_query, query)
        await self._ensure_voice(member, member.guild)
        player = self._player(member.guild.id)
        loaded: list[Track] = []
        for search in searches:
            track = await self._extract(search)
            track.requester_id = member.id
            track.requester_name = member.display_name
            player.queue.append(track)
            loaded.append(track)
        vc = member.guild.voice_client
        if vc and not vc.is_playing() and not vc.is_paused() and player.now is None:
            await self._advance(member.guild)
        else:
            await self.refresh_panel(member.guild)
        return loaded

    @commands.command(name="panel")
    @commands.has_permissions(manage_guild=True)
    async def panel(self, ctx: commands.Context) -> None:
        """Post the cute player dashboard in this channel."""
        player = self._player(ctx.guild.id)
        player.panel_channel_id = ctx.channel.id
        player.panel_message_id = None
        await self.refresh_panel(ctx.guild)
        await ctx.message.delete()

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        async with ctx.typing():
            try:
                loaded = await self.enqueue(ctx.author, query)
            except Exception as exc:
                await ctx.reply(f"couldn't play that: `{exc}`")
                return
        if len(loaded) == 1:
            await ctx.reply(f"queued **{loaded[0].title}**", delete_after=8)
        else:
            await ctx.reply(f"queued **{len(loaded)}** tracks from that link", delete_after=8)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not self._is_request_channel(message.channel):
            return
        if message.content.startswith("f!") or message.content.startswith("/"):
            return
        query = message.content.strip()
        if not query:
            return
        player = self._player(message.guild.id)
        player.panel_channel_id = message.channel.id
        try:
            await self.enqueue(message.author, query)
            await message.add_reaction("💗")
        except Exception:
            await message.add_reaction("❌")
        await self.refresh_panel(message.guild)

    async def ui_pause(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        player = self._player(interaction.guild.id)
        if vc is None or player.now is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        if vc.is_playing():
            player.seek = _elapsed(player)
            player.paused = True
            vc.pause()
        elif vc.is_paused():
            player.started_at = time.time()
            player.paused = False
            vc.resume()
        await interaction.response.edit_message(embed=self.build_embed(player), view=PlayerView(self))

    async def ui_skip(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        await interaction.response.defer()
        vc.stop()
        await self.refresh_panel(interaction.guild)

    async def ui_stop(self, interaction: discord.Interaction) -> None:
        player = self._player(interaction.guild.id)
        player.queue.clear()
        player.now = None
        player.paused = False
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.edit_message(embed=self.build_embed(player), view=PlayerView(self))

    async def ui_loop(self, interaction: discord.Interaction) -> None:
        player = self._player(interaction.guild.id)
        player.loop = not player.loop
        await interaction.response.edit_message(embed=self.build_embed(player), view=PlayerView(self))

    async def ui_shuffle(self, interaction: discord.Interaction) -> None:
        player = self._player(interaction.guild.id)
        items = list(player.queue)
        random.shuffle(items)
        player.queue = deque(items)
        await interaction.response.edit_message(embed=self.build_embed(player), view=PlayerView(self))
        await interaction.followup.send("shuffled", ephemeral=True) if False else None

    async def ui_volume(self, interaction: discord.Interaction, delta: int) -> None:
        player = self._player(interaction.guild.id)
        player.volume = min(1.0, max(0.05, player.volume + delta / 100))
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = player.volume
        await interaction.response.edit_message(embed=self.build_embed(player), view=PlayerView(self))

    async def ui_previous(self, interaction: discord.Interaction) -> None:
        player = self._player(interaction.guild.id)
        if not player.history:
            await interaction.response.send_message("no previous track", ephemeral=True)
            return
        if player.now:
            player.queue.appendleft(player.now)
        prev = player.history.pop()
        player.queue.appendleft(prev)
        player.now = None
        vc = interaction.guild.voice_client
        await interaction.response.defer()
        if vc:
            vc.stop()
        else:
            await self._advance(interaction.guild)

    async def ui_seek(self, interaction: discord.Interaction, delta: int) -> None:
        player = self._player(interaction.guild.id)
        if player.now is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        pos = max(0, _elapsed(player) + delta)
        if player.now.duration:
            pos = min(pos, max(0, player.now.duration - 1))
        player.seek = pos
        await interaction.response.defer()
        await self._play_current(interaction.guild)
        await self.refresh_panel(interaction.guild)

    async def ui_favorite(self, interaction: discord.Interaction) -> None:
        player = self._player(interaction.guild.id)
        if player.now is None:
            await interaction.response.send_message("nothing playing", ephemeral=True)
            return
        bag = player.favorites.setdefault(interaction.user.id, [])
        url = player.now.webpage_url
        if url in bag:
            await interaction.response.send_message("already in your favourites", ephemeral=True)
            return
        bag.append(url)
        await interaction.response.send_message(f"saved **{player.now.title}** 💗", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
