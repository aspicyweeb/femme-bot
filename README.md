# Your custom server bot

Cogs = features. Drop a new file in `cogs/` later and it loads on boot.

## Use
/quick channel:#roles title:sub roles exclusive:True roles:@owned @unowned @loser
/setup → /add → /publish if you want to go one role at a time

## Install once
1. discord.com/developers/applications → New Application → Bot
2. Token into `.env` as DISCORD_TOKEN
3. Intents ON: Server Members, Message Content
4. Invite with Manage Roles, Send Messages, Embed Links, Add Reactions, Read Message History, applications.commands
5. Drag the bot role above every role it assigns
6. Host that stays awake:

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py

## Grow it
Each new feature = one file in cogs/
- cogs/welcome.py
- cogs/verify.py
- cogs/logs.py
- cogs/tickets.py

Do not port everything on day one. Roles first. Then the next pain point.
