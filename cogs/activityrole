Replace your old activity cog with this. Download it or copy the whole file.

```python
"""Activity role cog.

The bot needs all of these or role updates silently do nothing:
- Server Members intent enabled in the developer portal AND in code
- Manage Roles
- The bot's highest role above the unlock role
- View Channel and Read Message History in every tracked channel

Message Content intent is not required.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

DATA_FILE = Path("/data/config.json")
KEEP_DAYS = 14
WINDOW_DAYS = 7
HISTORY_CAP = 20000
ARCHIVED_LIMIT = 300

TrackChannel = Union[
    discord.TextChannel,
    discord.ForumChannel,
    discord.VoiceChannel,
    discord.StageChannel,
    discord.Thread,
]


class DataError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_entries(raw) -> list:
    """Accept old timestamp strings and new {id, t, c} rows. Drop exact dupes."""
    if not isinstance(raw, list):
        return []
    entries = []
    seen_ids = set()
    seen_loose = set()
    for item in raw:
        channel_id = None
        message_id = None
        if isinstance(item, str):
            stamp = item
        elif isinstance(item, dict):
            stamp = item.get("t")
            if item.get("id"):
                message_id = str(item["id"])
            if item.get("c") is not None:
                channel_id = item.get("c")
        else:
            continue
        if parse_ts(stamp) is None:
            continue
        row = {"t": stamp}
        if message_id:
            if message_id in seen_ids:
                continue
            seen_ids.add(message_id)
            row["id"] = message_id
        else:
            if stamp in seen_loose:
                continue
            seen_loose.add(stamp)
        if channel_id is not None:
            try:
                row["c"] = int(channel_id)
            except (TypeError, ValueError):
                pass
        entries.append(row)
    return entries


def counts_toward(entry, cutoff: datetime, allowed) -> bool:
    stamp = parse_ts(entry.get("t"))
    if stamp is None or stamp <= cutoff:
        return False
    if allowed is None or entry.get("c") is None:
        return True
    try:
        return int(entry["c"]) in allowed
    except (TypeError, ValueError):
        return True


def count_recent(entries, cutoff: datetime, allowed=None) -> int:
    return sum(1 for entry in entries if counts_toward(entry, cutoff, allowed))


def prune(entries, cutoff: datetime) -> list:
    return [entry for entry in entries if parse_ts(entry.get("t")) and parse_ts(entry["t"]) > cutoff]


def add_entry(entries, seen_ids, message_id, when: datetime, channel_id: int) -> bool:
    mid = str(message_id)
    if mid in seen_ids:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seen_ids.add(mid)
    entries.append(
        {
            "id": mid,
            "t": when.astimezone(timezone.utc).isoformat(),
            "c": int(channel_id),
        }
    )
    return True


def merge_scanned(existing, scanned, window_start: datetime, drop_legacy: bool):
    """Merge scan rows into the saved map.

    scanned rows are (user_id, message_id, when, channel_id).
    A full scan drops old id-less rows inside the window so a second backfill
    does not double-count messages stored by the previous version.
    """
    buckets = {}
    seen = {}
    if isinstance(existing, dict):
        for uid, raw in existing.items():
            entries = normalize_entries(raw)
            if drop_legacy:
                kept = []
                for entry in entries:
                    stamp = parse_ts(entry.get("t"))
                    if entry.get("id"):
                        kept.append(entry)
                    elif stamp is not None and stamp <= window_start:
                        kept.append(entry)
                entries = kept
            key = str(uid)
            buckets[key] = entries
            seen[key] = {entry["id"] for entry in entries if entry.get("id")}

    added = 0
    for uid, message_id, when, channel_id in scanned:
        key = str(uid)
        bucket = buckets.setdefault(key, [])
        ids = seen.setdefault(key, set())
        if add_entry(bucket, ids, message_id, when, channel_id):
            added += 1

    prune_before = _now() - timedelta(days=KEEP_DAYS)
    for key in list(buckets):
        buckets[key] = prune(buckets[key], prune_before)
        if not buckets[key]:
            del buckets[key]
    return buckets, added


def is_watched(channel, watched: set) -> bool:
    if getattr(channel, "id", None) in watched:
        return True
    parent_id = getattr(channel, "parent_id", None)
    return parent_id in watched


def matched_channel_id(channel, watched: set) -> Optional[int]:
    # Prefer the channel itself, then a thread's parent. Text channels do not
    # have parent_id (that's the category), so this won't tag the category.
    if getattr(channel, "id", None) in watched:
        return int(channel.id)
    parent_id = getattr(channel, "parent_id", None)
    if parent_id in watched:
        return int(parent_id)
    return None


def passes_track(author, track_role_id, guild=None) -> bool:
    """False only when we can see the member and they lack the role.

    Unknown authors are counted. Skipping them made one leavers' message abort
    an entire channel scan.
    """
    if not track_role_id:
        return True
    member = author if getattr(author, "roles", None) else None
    if member is None and guild is not None:
        getter = getattr(guild, "get_member", None)
        if getter is not None:
            member = getter(getattr(author, "id", None))
    roles = getattr(member, "roles", None) if member is not None else None
    if not roles:
        return True
    return any(getattr(role, "id", None) == track_role_id for role in roles)


def load() -> dict:
    if not DATA_FILE.exists():
        return {}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataError(
            f"{DATA_FILE} is corrupt ({exc}). I did not overwrite it."
        ) from exc
    except OSError as exc:
        raise DataError(f"Couldn't read {DATA_FILE}: {exc}") from exc
    if not isinstance(data, dict):
        raise DataError(f"{DATA_FILE} is not a JSON object.")
    return data


def save(data: dict) -> None:
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)
    except OSError as exc:
        raise DataError(f"Couldn't save {DATA_FILE}: {exc}") from exc


def guild_bucket(data: dict, guild_id: int) -> dict:
    key = str(guild_id)
    bucket = data.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
        data[key] = bucket
    return bucket


def activity_config(data: dict, guild_id: int) -> Optional[dict]:
    bucket = data.get(str(guild_id))
    if not isinstance(bucket, dict):
        return None
    activity = bucket.get("activity")
    return activity if isinstance(activity, dict) else None


def id_list(values) -> list:
    found = []
    seen = set()
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number in seen:
            continue
        seen.add(number)
        found.append(number)
    return found


def unique_channels(channels) -> list:
    found = []
    seen = set()
    for channel in channels:
        if channel is None or channel.id in seen:
            continue
        seen.add(channel.id)
        found.append(channel)
    return found


def clip(text: str, limit: int = 1900) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def mentions_from_ids(prefix: str, values) -> str:
    ids = id_list(values)
    if not ids:
        return "none"
    return " ".join(f"<{prefix}{value}>" for value in ids)


class ActivityRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._data_lock = asyncio.Lock()
        self._check_lock = asyncio.Lock()

    async def cog_load(self):
        self.check_activity.start()

    def cog_unload(self):
        self.check_activity.cancel()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(error, app_commands.MissingPermissions):
            text = "You need administrator."
        elif isinstance(error, app_commands.NoPrivateMessage):
            text = "Use this in a server."
        elif isinstance(error, app_commands.CheckFailure):
            text = "You can't use that."
        else:
            log.exception("activity command failed", exc_info=original)
            text = f"Command failed: {original}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(clip(text), ephemeral=True)
            else:
                await interaction.response.send_message(clip(text), ephemeral=True)
        except discord.HTTPException:
            log.exception("failed to send activity command error")

    def _require_guild(self, interaction: discord.Interaction) -> Optional[discord.Guild]:
        return interaction.guild

    @app_commands.command(name="activitysetup", description="Set the activity role and who gets tracked")
    @app_commands.describe(
        role="Role that unlocks the locked channels",
        track_role="Only manage people who already have this role",
        channel="Channel that counts",
        required="Messages needed in the last 7 days",
        channel_2="Another channel that counts",
        channel_3="Another channel that counts",
        channel_4="Another channel that counts",
        channel_5="Another channel that counts",
        exempt_role="Role that always keeps the activity role",
        exempt_role_2="Another always-keep role",
        exempt_role_3="Another always-keep role",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def activitysetup(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        track_role: discord.Role,
        channel: TrackChannel,
        required: app_commands.Range[int, 1, 2000] = 40,
        channel_2: Optional[TrackChannel] = None,
        channel_3: Optional[TrackChannel] = None,
        channel_4: Optional[TrackChannel] = None,
        channel_5: Optional[TrackChannel] = None,
        exempt_role: Optional[discord.Role] = None,
        exempt_role_2: Optional[discord.Role] = None,
        exempt_role_3: Optional[discord.Role] = None,
    ):
        guild = self._require_guild(interaction)
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        problem = self._role_problem(guild, role, track_role)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return

        picked = unique_channels((channel, channel_2, channel_3, channel_4, channel_5))
        seen_roles = set()
        deduped_roles = []
        skipped_unlock = False
        for item in (exempt_role, exempt_role_2, exempt_role_3):
            if item is None:
                continue
            if item.id == role.id:
                skipped_unlock = True
                continue
            if item.id in seen_roles:
                continue
            seen_roles.add(item.id)
            deduped_roles.append(item)

        try:
            async with self._data_lock:
                data = load()
                bucket = guild_bucket(data, guild.id)
                prev = bucket.get("activity")
                if not isinstance(prev, dict):
                    prev = {}
                messages = prev.get("messages")
                if not isinstance(messages, dict):
                    messages = {}
                channels = id_list(prev.get("channels"))
                added = []
                for item in picked:
                    if item.id not in channels:
                        channels.append(item.id)
                        added.append(item.id)
                exempt_ids = id_list(prev.get("exempt_roles"))
                for item in deduped_roles:
                    if item.id not in exempt_ids:
                        exempt_ids.append(item.id)
                had_track = bool(prev.get("track_role_id"))
                track_changed = had_track and int(prev.get("track_role_id") or 0) != track_role.id
                backfilled = bool(prev.get("backfilled"))
                if added or track_changed:
                    backfilled = False
                activity = {
                    "role_id": role.id,
                    "track_role_id": track_role.id,
                    "required": int(required),
                    "channels": channels,
                    "exempt_roles": exempt_ids,
                    "messages": messages,
                    "backfilled": backfilled,
                }
                bucket["activity"] = activity
                save(data)
        except DataError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        unreadable = self._unreadable(guild, picked)
        lines = [
            "Saved.",
            f"Unlocks: {role.mention}",
            f"Tracks: {track_role.mention}",
            f"Required: {required} messages / 7 days",
            f"Channels: {mentions_from_ids('#', channels)}",
            f"Exempt: {mentions_from_ids('@&', exempt_ids)}",
            "Message history was kept. Add or remove channels with /activitychannel.",
        ]
        if added:
            lines.append("Newly added: " + mentions_from_ids("#", added))
        if skipped_unlock:
            lines.append("The unlock role was not added as exempt.")
        if not backfilled:
            why = "Tracked role changed. " if track_changed else ""
            lines.append(why + "I will not take the role away until a full 7-day /activitybackfill succeeds.")
        if unreadable:
            lines.append("I can't read history in " + " ".join(unreadable) + ".")
        await interaction.response.send_message(clip("\n".join(lines)), ephemeral=True)

    @app_commands.command(name="activitychannel", description="Add or remove a channel that counts")
    @app_commands.describe(channel="Text, forum, voice, stage, or thread", remove="Remove it instead of adding it")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def activitychannel(
        self,
        interaction: discord.Interaction,
        channel: TrackChannel,
        remove: bool = False,
    ):
        await self._mutate_list(interaction, "channels", channel, remove, "channel")

    @app_commands.command(name="activityexempt", description="Add or remove a role that always keeps access")
    @app_commands.describe(role="Role that always keeps the activity role", remove="Remove it instead of adding it")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def activityexempt(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        remove: bool = False,
    ):
        await self._mutate_list(interaction, "exempt_roles", role, remove, "exempt role")

    async def _mutate_list(self, interaction, key: str, obj, remove: bool, label: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        try:
            async with self._data_lock:
                data = load()
                activity = activity_config(data, guild.id)
                if activity is None:
                    reply = "Run /activitysetup first."
                else:
                    values = id_list(activity.get(key))
                    parent_id = getattr(obj, "parent_id", None)
                    if key == "exempt_roles" and not remove and obj.id == activity.get("role_id"):
                        reply = "That's the unlock role. Pick a different exempt role."
                    elif not remove and parent_id in values:
                        reply = "That thread's parent channel is already tracked, so its messages already count."
                    elif remove and obj.id not in values:
                        reply = f"That {label} is not in the list."
                    elif not remove and obj.id in values:
                        reply = f"That {label} is already in the list."
                    else:
                        if remove:
                            values = [value for value in values if value != obj.id]
                            note = ""
                            if key == "channels":
                                note = (
                                    "\nMessages tagged to that channel stop counting on the next check. "
                                    "Older saves with no channel tag still count until a full backfill."
                                )
                        else:
                            values.append(obj.id)
                            note = ""
                            if key == "channels":
                                activity["backfilled"] = False
                                note = "\nRole removal is paused until a full 7-day /activitybackfill succeeds."
                        activity[key] = values
                        save(data)
                        prefix = "#" if key == "channels" else "@&"
                        reply = (
                            f"{'Removed' if remove else 'Added'} {obj.mention}.\n"
                            f"Now: {mentions_from_ids(prefix, values)}{note}"
                        )
        except DataError as exc:
            reply = str(exc)
        await interaction.response.send_message(clip(reply), ephemeral=True)

    @app_commands.command(name="activitybackfill", description="Count recent messages in the tracked channels")
    @app_commands.describe(
        days="How many days back to read (7 enables role removal)",
        channel="Only scan this channel instead of every setup channel",
        channel_2="Another channel, if you are not scanning all of them",
        channel_3="Another channel, if you are not scanning all of them",
        channel_4="Another channel, if you are not scanning all of them",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def activitybackfill(
        self,
        interaction: discord.Interaction,
        days: app_commands.Range[int, 1, 7] = 7,
        channel: Optional[TrackChannel] = None,
        channel_2: Optional[TrackChannel] = None,
        channel_3: Optional[TrackChannel] = None,
        channel_4: Optional[TrackChannel] = None,
    ):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            async with self._data_lock:
                cfg = activity_config(load(), guild.id)
                configured = id_list(cfg.get("channels")) if cfg else []
                track_role_id = int(cfg["track_role_id"]) if cfg and cfg.get("track_role_id") else None
        except DataError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        if not configured:
            await interaction.followup.send("Run /activitysetup first.", ephemeral=True)
            return

        override = unique_channels((channel, channel_2, channel_3, channel_4))
        notes = []
        if override:
            source_ids = []
            for item in override:
                if item.id in configured or getattr(item, "parent_id", None) in configured:
                    source_ids.append(item.id)
                else:
                    notes.append(f"{item.mention} is not a setup channel.")
            if not source_ids:
                await interaction.followup.send(
                    clip("None of those channels are in the setup list.\n" + "\n".join(notes)),
                    ephemeral=True,
                )
                return
        else:
            source_ids = configured

        targets, unresolved, archive_capped = await self._expand_targets(guild, source_ids)
        if not targets:
            detail = "\n".join(unresolved) if unresolved else "I couldn't open any of them."
            await interaction.followup.send(clip("No channels to scan.\n" + detail), ephemeral=True)
            return

        await interaction.followup.send(
            f"Scanning {len(targets)} channel(s)/thread(s) from the last {days} day(s)…",
            ephemeral=True,
        )

        cutoff = _now() - timedelta(days=days)
        scanned = []
        forbidden = []
        capped = []
        configured_set = set(configured)
        for target in targets:
            # Tag with the setup channel, not the thread, or the count filter drops it.
            tag = matched_channel_id(target, configured_set)
            if tag is None:
                continue
            try:
                found, hit_cap = await self._scan_channel(target, cutoff, track_role_id, guild, tag)
            except discord.Forbidden:
                forbidden.append(target.mention)
                continue
            except discord.HTTPException as exc:
                forbidden.append(f"{target.mention} ({exc.status})")
                continue
            scanned.extend(found)
            if hit_cap:
                capped.append(target.mention)

        complete = (
            not override
            and days >= WINDOW_DAYS
            and not unresolved
            and not forbidden
            and not capped
            and not archive_capped
            and bool(targets)
        )
        try:
            missing = False
            async with self._data_lock:
                data = load()
                activity = activity_config(data, guild.id)
                if activity is None:
                    missing = True
                else:
                    # Only a complete scan replaces id-less rows from the old cog.
                    messages, added = merge_scanned(
                        activity.get("messages"),
                        scanned,
                        cutoff,
                        drop_legacy=complete,
                    )
                    activity["messages"] = messages
                    if complete:
                        activity["backfilled"] = True
                    save(data)
                    backfilled = bool(activity.get("backfilled"))
            if missing:
                await interaction.followup.send("Config disappeared mid-scan. Run /activitysetup.", ephemeral=True)
                return
        except DataError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        lines = [
            "Backfill done.",
            f"Messages found: {len(scanned)}",
            f"Newly saved: {added}",
            "Scanned: " + " ".join(target.mention for target in targets[:30]),
        ]
        if len(targets) > 30:
            lines.append(f"…and {len(targets) - 30} more.")
        if backfilled and complete:
            lines.append("Role removal is on. /activitycheck will take the role from anyone under the count.")
        elif backfilled:
            lines.append("Role removal was already on. This partial scan did not turn it off.")
        else:
            lines.append("Role removal is still off. Run this with no channel arguments and days=7, with no errors.")
        if notes:
            lines.append("Skipped: " + " ".join(notes))
        if unresolved:
            lines.append("Couldn't open: " + " ".join(unresolved))
        if forbidden:
            lines.append("No permission: " + " ".join(forbidden))
        if capped:
            lines.append(
                "Hit the "
                + str(HISTORY_CAP)
                + " message cap in "
                + " ".join(capped)
                + ". Counts there may be low."
            )
        if archive_capped:
            lines.append("Stopped after a lot of archived threads. Some older threads may be missing.")
        await interaction.followup.send(clip("\n".join(lines)), ephemeral=True)

    @app_commands.command(name="activitycheck", description="Update activity roles now")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def activitycheck(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            text = await self.run_check(interaction.guild_id)
        except Exception as exc:
            log.exception("manual activity check failed")
            text = f"Check failed: {exc}"
        await interaction.followup.send(clip(text), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or message.is_system():
            return
        try:
            async with self._data_lock:
                data = load()
                activity = activity_config(data, message.guild.id)
                if activity is None:
                    return
                watched = set(id_list(activity.get("channels")))
                channel_id = matched_channel_id(message.channel, watched)
                if channel_id is None:
                    return
                track_role_id = activity.get("track_role_id")
                try:
                    track_role_id = int(track_role_id) if track_role_id else None
                except (TypeError, ValueError):
                    track_role_id = None
                if not passes_track(message.author, track_role_id, message.guild):
                    return
                messages = activity.get("messages")
                if not isinstance(messages, dict):
                    messages = {}
                    activity["messages"] = messages
                uid = str(message.author.id)
                entries = normalize_entries(messages.get(uid))
                seen = {entry["id"] for entry in entries if entry.get("id")}
                when = message.created_at
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if not add_entry(entries, seen, message.id, when, channel_id):
                    return
                messages[uid] = prune(entries, _now() - timedelta(days=KEEP_DAYS))
                save(data)
        except DataError:
            log.exception("failed to record activity message")

    @tasks.loop(minutes=30)
    async def check_activity(self):
        try:
            result = await self.run_check()
        except Exception:
            log.exception("activity check failed")
            return
        log.info("activity check: %s", result.replace("\n", " | "))

    @check_activity.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @check_activity.error
    async def check_activity_error(self, error: BaseException):
        log.exception("activity loop crashed", exc_info=error)

    async def run_check(self, only_guild_id: Optional[int] = None) -> str:
        if self._check_lock.locked():
            return "A check is already running."
        async with self._check_lock:
            try:
                async with self._data_lock:
                    data = load()
                    jobs = []
                    dirty = False
                    for gid_str, guild_data in list(data.items()):
                        if only_guild_id is not None and gid_str != str(only_guild_id):
                            continue
                        if not isinstance(guild_data, dict):
                            continue
                        activity = guild_data.get("activity")
                        if not isinstance(activity, dict):
                            continue
                        if self._prune_saved(activity):
                            dirty = True
                        try:
                            jobs.append((int(gid_str), self._snapshot(activity)))
                        except (TypeError, ValueError):
                            continue
                    if dirty:
                        save(data)
            except DataError as exc:
                return str(exc)

            if not jobs:
                return "Nothing to check. Run /activitysetup first."

            blocks = []
            for gid, snap in jobs:
                guild = self.bot.get_guild(gid)
                if guild is None:
                    continue
                try:
                    blocks.append(await self._sync_guild(guild, snap))
                except Exception as exc:
                    log.exception("activity sync failed for guild %s", gid)
                    blocks.append(f"{guild.name}: {exc}")
            if not blocks:
                return "I couldn't see that server. Is the bot in it and finished starting?"
            return clip("\n\n".join(blocks))

    async def _sync_guild(self, guild: discord.Guild, snap: dict) -> str:
        if guild.unavailable:
            return f"{guild.name}: server is unavailable. No roles were changed."
        if not snap["channels"]:
            return f"{guild.name}: no channels configured. No roles were changed."

        member_problem = await self._ensure_members(guild)
        if member_problem:
            return member_problem

        role = guild.get_role(snap["role_id"])
        track = guild.get_role(snap["track_role_id"])
        if role is None:
            return f"{guild.name}: the unlock role was deleted. Run /activitysetup again."
        if track is None:
            return f"{guild.name}: the tracked role was deleted. Run /activitysetup again."

        me = guild.me
        if me is None and self.bot.user is not None:
            try:
                me = await guild.fetch_member(self.bot.user.id)
            except discord.HTTPException:
                me = None
        if me is None:
            return f"{guild.name}: I can't see my own member. No roles were changed."
        if not me.guild_permissions.manage_roles:
            return f"{guild.name}: I need Manage Roles. No roles were changed."
        if role.managed:
            return f"{guild.name}: {role.name} is managed by an integration. I can't assign it."
        if role.is_default():
            return f"{guild.name}: the unlock role can't be @everyone."
        if role >= me.top_role:
            return f"{guild.name}: move my highest role above {role.mention}. No roles were changed."

        exempt_roles = []
        missing_exempt = []
        for role_id in snap["exempt_ids"]:
            found = guild.get_role(role_id)
            if found is None:
                missing_exempt.append(str(role_id))
            else:
                exempt_roles.append(found)
        exempt_ids = {item.id for item in exempt_roles}

        added = []
        removed = []
        failed = []
        skipped_hierarchy = 0
        for member in list(guild.members):
            if member.bot or getattr(member, "pending", False):
                continue
            is_exempt = any(item.id in exempt_ids for item in member.roles)
            if track not in member.roles and not is_exempt:
                continue
            if member.top_role >= me.top_role:
                skipped_hierarchy += 1
                continue
            has_role = role in member.roles
            if is_exempt:
                if not has_role:
                    try:
                        await member.add_roles(role, reason="Activity exempt")
                        added.append(member)
                    except discord.HTTPException as exc:
                        failed.append(f"{member} exempt ({getattr(exc, 'status', 'error')})")
                continue
            recent = snap["counts"].get(member.id, 0)
            try:
                if recent >= snap["required"] and not has_role:
                    await member.add_roles(role, reason=f"Activity {recent}/{snap['required']} in 7d")
                    added.append(member)
                elif snap["can_remove"] and recent < snap["required"] and has_role:
                    await member.remove_roles(role, reason=f"Activity {recent}/{snap['required']} in 7d")
                    removed.append(member)
            except discord.HTTPException as exc:
                failed.append(f"{member} ({getattr(exc, 'status', 'error')})")

        lines = [
            f"**{guild.name}**",
            f"Added {len(added)}: {self._names(added)}",
            f"Removed {len(removed)}: {self._names(removed)}",
        ]
        if not snap["can_remove"]:
            lines.append("Did not remove anyone. Run /activitybackfill for 7 days with no channel filter first.")
        if skipped_hierarchy:
            lines.append(f"Skipped {skipped_hierarchy} member(s) whose top role is above mine.")
        if missing_exempt:
            lines.append("Exempt role IDs that no longer exist: " + ", ".join(missing_exempt))
        if failed:
            lines.append("Failed: " + "; ".join(failed[:8]))
        log.info("activity guild=%s added=%s removed=%s", guild.id, len(added), len(removed))
        return "\n".join(lines)

    async def _ensure_members(self, guild: discord.Guild) -> Optional[str]:
        count = guild.member_count or 0
        if count and len(guild.members) + 5 >= count:
            return None
        try:
            await guild.chunk()
        except discord.ClientException:
            return (
                f"{guild.name}: Server Members intent is off. Turn it on in the developer portal "
                "and in the bot's Intents, then restart. No roles were changed."
            )
        except discord.HTTPException as exc:
            return f"{guild.name}: couldn't load members ({exc}). No roles were changed."
        missing = (guild.member_count or 0) - len(guild.members)
        if missing > 5:
            return (
                f"{guild.name}: member list is still incomplete "
                f"({len(guild.members)}/{guild.member_count}). No roles were changed."
            )
        return None

    def _snapshot(self, activity: dict) -> dict:
        cutoff = _now() - timedelta(days=WINDOW_DAYS)
        allowed = set(id_list(activity.get("channels")))
        counts = {}
        messages = activity.get("messages")
        if isinstance(messages, dict):
            for uid, raw in messages.items():
                try:
                    uid_int = int(uid)
                except (TypeError, ValueError):
                    continue
                counts[uid_int] = count_recent(normalize_entries(raw), cutoff, allowed)
        return {
            "role_id": int(activity["role_id"]),
            "track_role_id": int(activity["track_role_id"]),
            "required": int(activity.get("required") or 40),
            "exempt_ids": set(id_list(activity.get("exempt_roles"))),
            "channels": allowed,
            "counts": counts,
            "can_remove": bool(activity.get("backfilled")),
        }

    def _prune_saved(self, activity: dict) -> bool:
        messages = activity.get("messages")
        if not isinstance(messages, dict):
            activity["messages"] = {}
            return True
        cutoff = _now() - timedelta(days=KEEP_DAYS)
        updated = {}
        changed = False
        for uid, raw in messages.items():
            entries = prune(normalize_entries(raw), cutoff)
            if entries:
                updated[str(uid)] = entries
            if entries != raw:
                changed = True
        if set(updated) != set(str(uid) for uid in messages):
            changed = True
        if changed:
            activity["messages"] = updated
        return changed

    def _role_problem(self, guild: discord.Guild, role: discord.Role, track_role: discord.Role) -> Optional[str]:
        if role.id == track_role.id:
            return (
                "The unlock role and the tracked role can't be the same. "
                "After I remove it, that person is no longer tracked and can never earn it back."
            )
        if role.is_default():
            return "The unlock role can't be @everyone."
        if role.managed:
            return "That unlock role is managed by an integration. I can't assign it."
        me = guild.me
        if me is None:
            return "I can't see my own member in this server yet. Restart me and try again."
        if not me.guild_permissions.manage_roles:
            return "I need the Manage Roles permission."
        if role >= me.top_role:
            return f"Move my highest role above {role.mention}, or I can't assign it."
        return None

    def _unreadable(self, guild: discord.Guild, channels) -> list:
        me = guild.me
        if me is None:
            return []
        bad = []
        for channel in channels:
            perms = channel.permissions_for(me)
            if not perms.view_channel or not perms.read_message_history:
                bad.append(channel.mention)
        return bad

    def _names(self, members) -> str:
        if not members:
            return "none"
        shown = [member.mention for member in members[:12]]
        extra = len(members) - len(shown)
        text = " ".join(shown)
        if extra:
            text += f" +{extra}"
        return text

    async def _expand_targets(self, guild: discord.Guild, channel_ids):
        targets = []
        seen = set()
        unresolved = []
        archive_capped = False

        def add(channel):
            if channel is None or channel.id in seen or not hasattr(channel, "history"):
                return
            seen.add(channel.id)
            targets.append(channel)

        for channel_id in channel_ids:
            channel = guild.get_channel(channel_id) or guild.get_thread(channel_id)
            if channel is None:
                try:
                    channel = await guild.fetch_channel(channel_id)
                except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
                    unresolved.append(f"<#{channel_id}> ({exc.__class__.__name__})")
                    continue
            if isinstance(channel, discord.Thread):
                add(channel)
                continue
            if isinstance(channel, discord.ForumChannel):
                for thread in list(getattr(channel, "threads", ())):
                    add(thread)
                archived, capped = await self._archived(channel)
                archive_capped = archive_capped or capped
                for thread in archived:
                    add(thread)
                continue
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
                add(channel)
                for thread in list(getattr(channel, "threads", ())):
                    add(thread)
                if isinstance(channel, discord.TextChannel):
                    archived, capped = await self._archived(channel)
                    archive_capped = archive_capped or capped
                    for thread in archived:
                        add(thread)
                continue
            unresolved.append(f"<#{channel_id}> is not a text channel")
        return targets, unresolved, archive_capped

    async def _archived(self, channel):
        found = []
        capped = False
        for private in (False, True):
            got = 0
            try:
                iterator = channel.archived_threads(
                    limit=ARCHIVED_LIMIT,
                    private=private,
                    joined=private,
                )
                async for thread in iterator:
                    found.append(thread)
                    got += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
            if got >= ARCHIVED_LIMIT:
                capped = True
        return found, capped

    async def _scan_channel(self, channel, cutoff: datetime, track_role_id, guild, tag: int):
        found = []
        seen = 0
        # after= makes discord.py walk oldest-first. limit must stay None.
        # The old limit=500 kept the oldest 500 and dropped the newest ones.
        async for message in channel.history(limit=None, after=cutoff, oldest_first=True):
            seen += 1
            if seen > HISTORY_CAP:
                return found, True
            if message.author.bot or message.is_system():
                continue
            if not passes_track(message.author, track_role_id, guild):
                continue
            when = message.created_at
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            found.append((str(message.author.id), str(message.id), when, int(tag)))
        return found, False


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityRole(bot))
```
