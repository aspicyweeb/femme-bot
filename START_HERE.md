# Start here. Do not skip steps.

Do one numbered item. Stop. Check it worked. Then do the next.

You are on a phone. The Discord app-creation part works in mobile Safari.
The "make the bot stay online" part needs a computer or a website host.
Do Steps 1–6 tonight. Stop after the bot joins your server.
Running the code is Step 7. We can do that next message.

---

## Step 1 — Open the developer site

In Safari (not the Discord app):

https://discord.com/developers/applications

Log in with the same Discord account that owns / can manage the server.

You should see a page titled Applications and a button that says
**New Application**.

If you see that button, Step 1 is done.

---

## Step 2 — Make the application

1. Tap **New Application**.
2. Name it. This is the bot's public name.
   Example: `bubbles` or `roles`
3. Agree to the terms.
4. Tap **Create**.

You are now on that app's page. Left sidebar has
General Information, Bot, OAuth2, etc.

Step 2 is done.

---

## Step 3 — Turn it into a bot

1. Left sidebar → **Bot**.
2. Tap **Add Bot** → **Yes, do it!**
3. You should now see a bot username and an avatar placeholder.
4. Under Username you can rename it if you want.
5. Optional: tap the avatar to upload a pfp.

Stay on this Bot page.

Step 3 is done.

---

## Step 4 — Copy the token. Hide it.

Still on **Bot**:

1. Find **Token**.
2. Tap **Reset Token** / **Copy**.
3. Paste it into your Notes app for now.
4. Do NOT send it in Discord. Do NOT screenshot it into a chat.
   Anyone with that token *is* your bot.

The token looks like a long garbage string.
That is normal.

Step 4 is done when the string is in Notes.

---

## Step 5 — Turn two switches on

Still on **Bot**, scroll to
**Privileged Gateway Intents**.

Turn ON:

- SERVER MEMBERS INTENT
- MESSAGE CONTENT INTENT

Tap **Save Changes**.

If those two are green/on, Step 5 is done.

---

## Step 6 — Invite the bot to your server

1. Left sidebar → **OAuth2** → **URL Generator**.
2. Scopes. Check only:
   - `bot`
   - `applications.commands`
3. Bot Permissions. Check only:
   - Manage Roles
   - Send Messages
   - Embed Links
   - Add Reactions
   - Read Message History
   - Use External Emojis
   - View Channels
4. Scroll down. Copy the generated URL.
5. Paste it in Safari. Pick your server. Authorize.

Go look at your Discord server member list.
A new bot user should be sitting there, offline.

**Then this extra bit or roles will silently fail:**

Server Settings → Roles.

Drag the bot's role **above** owned, unowned, loser, findom, all of them.
Save.

Step 6 is done when:
- the bot is in the member list
- its role is higher than the roles it will hand out

**Stop here tonight if you want.**
The bot is created. It just isn't running yet, so it will show Offline.
That is expected.

---

## Step 7 — Make it stay online

The code I wrote does nothing until a computer runs `python bot.py`
and leaves it running.

Options, from easiest to "I have a PC":

A. A friend / you on a computer, later
B. A free/cheap host (Railway or Render) — we do this together next
C. Your own PC that never sleeps

Do not try to run this on the iPhone.

When you are ready for Step 7, say
"ready for hosting"
and tell me if you have a computer or only the phone.

---

## What you do NOT do yet

- Do not type `/quick` yet. Offline bots ignore slash commands.
- Do not delete Carl or MEE6 yet.
- Do not paste the token anywhere except Notes and, later, a `.env` file.
EOF
