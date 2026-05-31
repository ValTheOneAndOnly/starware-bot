import discord
from discord.ext import commands
from flask import Flask, request, jsonify
import json, hashlib, random, string, threading, subprocess, time, datetime, os, asyncio
from pathlib import Path

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_PORT = int(os.environ.get("PORT", 5000))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
BUILD_CACHE_BUST = "v4"
AUTHORIZED_USERS = [1436458270759063603]

BUYER_ROLE_NAME = "Buyer"
ANTIRAID_JOIN_LIMIT = 5
ANTIRAID_WINDOW = 10

app = Flask(__name__)

import psycopg2
import psycopg2.extras

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    cur.execute("INSERT INTO state (id, data) VALUES (1, '{}') ON CONFLICT DO NOTHING")
    conn.commit()
    cur.close()
    conn.close()

def load_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT data FROM state WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return {"users": {}, "warnings": {}, "antiraid": False}

def save_data(data):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE state SET data = %s WHERE id = 1", (json.dumps(data),))
    conn.commit()
    cur.close()
    conn.close()

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def get_hwid():
    try:
        r = subprocess.run('wmic diskdrive get serialnumber', capture_output=True, text=True, shell=True)
        serial = r.stdout.strip().split('\n')[-1].strip()
        r2 = subprocess.run('wmic nic where PhysicalAdapter=True get MACAddress', capture_output=True, text=True, shell=True)
        macs = [l.strip() for l in r2.stdout.split('\n') if l.strip() and not l.strip().startswith('MAC')]
        mac = macs[0] if macs else ''
        raw = f'{serial}-{mac}'
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    except:
        return "unknown"

MASTER_HWID = get_hwid()

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.before_request
def log_all():
    if request.path != "/ping":
        print(f"REQ: {request.method} {request.path} args={dict(request.args)}")
        if request.data:
            try:
                print(f"BODY: {request.get_json(force=True)}")
            except:
                print(f"BODY: {request.data[:300]}")

@app.route("/ping", methods=["GET", "OPTIONS"])
def ping():
    if request.method == "OPTIONS":
        return jsonify({})
    return jsonify({"status": "ok", "message": "Starware API is live"})

@app.route("/login", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/login", methods=["GET", "POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return jsonify({})
    if request.method == "GET":
        body = request.args
        print(f"LOGIN GET args: {dict(body)}")
    else:
        try:
            body = request.get_json(force=True)
            print(f"LOGIN JSON: {dict(body)}")
        except:
            body = request.form
            print(f"LOGIN FORM: {dict(body)}")
    username = body.get("username") or body.get("user") or ""
    username = username.strip().lower()
    password = body.get("password") or body.get("pass") or body.get("key") or ""
    password = password.strip()
    hwid = body.get("hwid") or ""

    if MASTER_HWID != "unknown" and hwid == MASTER_HWID:
        return jsonify({"status": "ok", "message": "Authorized (owner)"})

    if not username or not password or not hwid:
        return jsonify({"status": "error", "message": "Missing fields"})

    db = load_data()
    user = db.get("users", {}).get(username)
    if not user:
        return jsonify({"status": "error", "message": "Invalid username or password"})

    if user["password"] != hash_password(password):
        return jsonify({"status": "error", "message": "Invalid username or password"})

    if user.get("banned"):
        return jsonify({"status": "banned", "message": "Your banned buddy nice try"})

    if user.get("lifetime"):
        pass
    elif user.get("subscription_end"):
        if time.time() > user["subscription_end"]:
            return jsonify({"status": "expired", "message": "key expired. Renew your key today!"})
    else:
        return jsonify({"status": "error", "message": "No active subscription"})

    bound = user.get("hwid")
    if bound is None:
        user["hwid"] = hwid
        save_data(db)
        return jsonify({"status": "ok", "message": "Logged in and HWID bound"})
    elif bound == hwid:
        return jsonify({"status": "ok", "message": "Logged in"})
    else:
        return jsonify({"status": "error", "message": "Account already bound to another device"})

@app.route("/check", methods=["GET", "OPTIONS"])
@app.route("/api/check", methods=["GET", "OPTIONS"])
def check_hwid():
    if request.method == "OPTIONS":
        return jsonify({})
    hwid = request.args.get("hwid", "")
    if MASTER_HWID != "unknown" and hwid == MASTER_HWID:
        return jsonify({"status": "ok", "message": "Authorized (owner)"})
    db = load_data()
    for uname, user in db.get("users", {}).items():
        if user.get("hwid") == hwid:
            if user.get("banned"):
                return jsonify({"status": "banned", "message": "Your banned buddy nice try"})
            if user.get("lifetime"):
                return jsonify({"status": "ok", "message": f"Authorized as {uname} (lifetime)"})
            if user.get("subscription_end") and time.time() > user["subscription_end"]:
                return jsonify({"status": "expired", "message": "key expired. Renew your key today!"})
            return jsonify({"status": "ok", "message": f"Authorized as {uname}"})
    return jsonify({"status": "denied", "message": "Not authorized"})

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

TICKET_CATEGORY_NAME = "Tickets"

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    print(f"Master HWID: {MASTER_HWID}")
    bot.add_view(BuyView())

@bot.event
async def on_member_join(member):
    db = load_data()
    if not db.get("antiraid"):
        return
    now = time.time()
    joins = db.setdefault("join_log", [])
    joins.append(now)
    db["join_log"] = [t for t in joins if now - t < ANTIRAID_WINDOW]
    save_data(db)
    if len(db["join_log"]) >= ANTIRAID_JOIN_LIMIT:
        guild = member.guild
        for channel in guild.text_channels:
            try:
                await channel.set_permissions(guild.default_role, send_messages=False)
            except:
                pass
        db["antiraid_active"] = True
        save_data(db)
        for uid in AUTHORIZED_USERS:
            m = guild.get_member(uid)
            if m:
                try:
                    await m.send(f"Raid detected! {len(db['join_log'])} joins in {ANTIRAID_WINDOW}s. Channels locked.")
                except:
                    pass

@bot.command(name="panel")
async def panel(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    embed = discord.Embed(
        title="Starware - Purchase Access",
        description=(
            "Click the button below to open a purchase ticket.\n"
            "Our staff will assist you with payment and setup.\n\n"
            "**Each account is HWID-locked** - one device per purchase."
        ),
        color=0xffd700
    )
    embed.set_footer(text="Starware | The ultimate Roblox injector")
    await ctx.send(embed=embed, view=BuyView())

@bot.command(name="addbuyer")
async def addbuyer(ctx, member: discord.Member = None, username: str = None, password: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not member or not username or not password:
        return await ctx.reply("Usage: !addbuyer @user <username> <password>")
    username = username.strip().lower()
    db = load_data()
    if username in db.setdefault("users", {}):
        return await ctx.reply("User already exists.")
    db["users"][username] = {
        "password": hash_password(password),
        "password_plain": password,
        "hwid": None,
        "lifetime": False,
        "subscription_end": time.time() + 30 * 86400,
        "discord_id": str(member.id),
        "banned": False,
        "created_by": ctx.author.name
    }
    save_data(db)
    role = discord.utils.get(ctx.guild.roles, name=BUYER_ROLE_NAME)
    if not role:
        role = await ctx.guild.create_role(name=BUYER_ROLE_NAME)
    await member.add_roles(role)
    embed = discord.Embed(title="Buyer Account Created", color=0x00ff00)
    embed.add_field(name="Discord User", value=member.mention)
    embed.add_field(name="Username", value=f"`{username}`")
    embed.add_field(name="Password", value=f"`{password}`")
    embed.add_field(name="Subscription", value="30 days (default)")
    embed.add_field(name="Download", value="https://www.mediafire.com/file/u6pfgt7d199fh3n/Starware.zip/file", inline=False)
    await ctx.reply(embed=embed)

@bot.command(name="createuser")
async def createuser(ctx, username: str = None, password: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not username or not password:
        return await ctx.reply("Usage: !createuser <username> <password>")
    username = username.strip().lower()
    db = load_data()
    if username in db.setdefault("users", {}):
        return await ctx.reply("User already exists.")
    db["users"][username] = {
        "password": hash_password(password),
        "password_plain": password,
        "hwid": None,
        "lifetime": False,
        "subscription_end": None,
        "discord_id": None,
        "banned": False,
        "created_by": ctx.author.name
    }
    save_data(db)
    await ctx.reply(f"User `{username}` created successfully! (no subscription set)")

@bot.command(name="listusers")
async def listusers(ctx, username: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    db = load_data()
    if username:
        username = username.strip().lower()
        u = db.get("users", {}).get(username)
        if not u:
            return await ctx.reply("User not found.")
        hwid_status = f"bound (`{u['hwid'][:12]}...`)" if u.get("hwid") else "unbound"
        if u.get("banned"):
            sub_status = "BANNED"
        elif u.get("lifetime"):
            sub_status = "Lifetime"
        elif u.get("subscription_end") and time.time() < u["subscription_end"]:
            remaining = int(u["subscription_end"]) - int(time.time())
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            sub_status = f"Active ({days}d {hours}h left)"
        elif u.get("subscription_end"):
            sub_status = "Expired"
        else:
            sub_status = "None"
        lines = []
        lines.append(f"**{username}**")
        lines.append(f"Password: `{u.get('password_plain', 'N/A')}`")
        lines.append(f"Status: {hwid_status}, {sub_status}")
        if u.get("discord_id"):
            lines.append(f"Discord: <@{u['discord_id']}>")
        lines.append(f"Banned: {'Yes' if u.get('banned') else 'No'}")
        await ctx.reply("\n".join(lines))
        return
    users = db.get("users", {})
    if not users:
        return await ctx.reply("No users.")
    lines = []
    for uname, u in users.items():
        hwid = f"HWID: bound (`{u['hwid'][:12]}...`)" if u.get("hwid") else "HWID: free"
        pw = u.get("password_plain", "N/A")
        if u.get("banned"):
            sub = "BANNED"
        elif u.get("lifetime"):
            sub = "Lifetime"
        elif u.get("subscription_end") and time.time() < u["subscription_end"]:
            remaining = int(u["subscription_end"]) - int(time.time())
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            sub = f"{days}d {hours}h left"
        elif u.get("subscription_end"):
            sub = "Expired"
        else:
            sub = "No sub"
        discord_info = f"<@{u['discord_id']}>" if u.get("discord_id") else ""
        line = f"**{uname}** | PW: `{pw}` | {hwid} | {sub} {discord_info}"
        lines.append(line)
    for chunk in [lines[i:i+10] for i in range(0, len(lines), 10)]:
        await ctx.reply("\n".join(chunk))

@bot.command(name="unbind")
async def unbind(ctx, username: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not username:
        return await ctx.reply("Usage: !unbind <username>")
    username = username.strip().lower()
    db = load_data()
    user = db.get("users", {}).get(username)
    if not user:
        return await ctx.reply("User not found.")
    user["hwid"] = None
    save_data(db)
    await ctx.reply(f"Unbound `{username}` from their HWID.")

@bot.command(name="stats")
async def stats(ctx, username: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    db = load_data()
    if username:
        username = username.strip().lower()
        user = db.get("users", {}).get(username)
        if not user:
            return await ctx.reply("User not found.")
        hwid_status = f"bound (`{user['hwid'][:12]}...`)" if user.get("hwid") else "unbound"
        if user.get("banned"):
            sub_status = "BANNED"
        elif user.get("lifetime"):
            sub_status = "Lifetime (never expires)"
        elif user.get("subscription_end") and time.time() < user["subscription_end"]:
            remaining = int(user["subscription_end"]) - int(time.time())
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            sub_status = f"Active ({days}d {hours}h remaining)"
        elif user.get("subscription_end"):
            sub_status = "Expired"
        else:
            sub_status = "None"
        embed = discord.Embed(title=f"Stats for {username}", color=0xffd700)
        embed.add_field(name="Password", value=f"`{user.get('password_plain', 'N/A')}`")
        embed.add_field(name="Subscription", value=sub_status)
        embed.add_field(name="HWID", value=hwid_status)
        embed.add_field(name="Banned", value="Yes" if user.get("banned") else "No")
        embed.add_field(name="Discord ID", value=user.get("discord_id") or "Not linked")
        embed.add_field(name="Created by", value=user.get("created_by", "Unknown"))
        await ctx.reply(embed=embed)
    else:
        users = db.get("users", {})
        total = len(users)
        bound = sum(1 for u in users.values() if u.get("hwid"))
        lifetime = sum(1 for u in users.values() if u.get("lifetime"))
        active = sum(1 for u in users.values() if u.get("subscription_end") and time.time() < u["subscription_end"] and not u.get("lifetime"))
        banned = sum(1 for u in users.values() if u.get("banned"))
        embed = discord.Embed(title="Star Account Stats", color=0xffd700)
        embed.add_field(name="Total Accounts", value=str(total))
        embed.add_field(name="HWID-Bound", value=str(bound))
        embed.add_field(name="Lifetime", value=str(lifetime))
        embed.add_field(name="Active (sub)", value=str(active))
        embed.add_field(name="Banned", value=str(banned))
        embed.add_field(name="Unbound", value=str(total - bound))
        await ctx.reply(embed=embed)

@bot.command(name="renew")
async def renew(ctx, username: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not username:
        return await ctx.reply("Usage: !renew <username>")
    username = username.strip().lower()
    db = load_data()
    user = db.get("users", {}).get(username)
    if not user:
        return await ctx.reply("User not found.")
    now = time.time()
    old_end = user.get("subscription_end")
    if old_end and old_end > now:
        user["subscription_end"] = old_end + 30 * 86400
    else:
        user["subscription_end"] = now + 30 * 86400
    user["lifetime"] = False
    save_data(db)
    await ctx.reply(f"Renewed `{username}` for 30 days. Expires <t:{int(user['subscription_end'])}:R>.")

@bot.command(name="extend")
async def extend(ctx, username: str = None, days: int = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not username or not days:
        return await ctx.reply("Usage: !extend <username> <days>")
    username = username.strip().lower()
    db = load_data()
    user = db.get("users", {}).get(username)
    if not user:
        return await ctx.reply("User not found.")
    now = time.time()
    old_end = user.get("subscription_end")
    if old_end and old_end > now:
        user["subscription_end"] = old_end + days * 86400
    else:
        user["subscription_end"] = now + days * 86400
    user["lifetime"] = False
    save_data(db)
    await ctx.reply(f"Extended `{username}` by {days} days. Expires <t:{int(user['subscription_end'])}:R>.")

@bot.command(name="setlifetime")
async def setlifetime(ctx, *, args: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not args:
        return await ctx.reply("Usage: `!setlifetime <username>` or `!setlifetime @user <username>`")
    parts = args.strip().split()
    member = None
    username = None
    if parts[0].startswith("<@") and len(parts) >= 2:
        try:
            member = await commands.MemberConverter().convert(ctx, parts[0])
            username = " ".join(parts[1:])
        except:
            member = None
    if not member:
        username = args.strip()
    username = username.strip().lower()
    password = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    db = load_data()
    if username in db.setdefault("users", {}):
        return await ctx.reply("User already exists. Use !extend or convert manually.")
    db["users"][username] = {
        "password": hash_password(password),
        "password_plain": password,
        "hwid": None,
        "lifetime": True,
        "subscription_end": None,
        "discord_id": str(member.id) if member else None,
        "banned": False,
        "created_by": ctx.author.name
    }
    save_data(db)
    if member:
        role = discord.utils.get(ctx.guild.roles, name=BUYER_ROLE_NAME)
        if not role:
            role = await ctx.guild.create_role(name=BUYER_ROLE_NAME)
        await member.add_roles(role)
    embed = discord.Embed(title="Lifetime License Created", color=0x00ff00)
    embed.add_field(name="Username", value=f"`{username}`")
    embed.add_field(name="Password", value=f"`{password}`")
    embed.add_field(name="Download", value="https://www.mediafire.com/file/u6pfgt7d199fh3n/Starware.zip/file", inline=False)
    if member:
        embed.add_field(name="Discord User", value=member.mention)
    embed.set_footer(text="Share these credentials with the buyer")
    await ctx.reply(embed=embed)

@bot.command(name="deleteuser")
async def deleteuser(ctx, username: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not username:
        return await ctx.reply("Usage: !deleteuser <username>")
    username = username.strip().lower()
    db = load_data()
    if username not in db.get("users", {}):
        return await ctx.reply("User not found.")
    del db["users"][username]
    save_data(db)
    await ctx.reply(f"Deleted user `{username}`.")

@bot.command(name="antiraid")
async def antiraid(ctx, mode: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if mode not in ("on", "off"):
        return await ctx.reply("Usage: !antiraid on/off")
    db = load_data()
    db["antiraid"] = mode == "on"
    if mode == "off":
        db["antiraid_active"] = False
    save_data(db)
    await ctx.reply(f"Antiraid mode is now **{mode.upper()}**.")

@bot.command(name="lockdown")
async def lockdown(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    count = 0
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False)
            count += 1
        except:
            pass
    await ctx.reply(f"Locked **{count}** text channels.")

@bot.command(name="unlock")
async def unlock(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    count = 0
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=None)
            count += 1
        except:
            pass
    await ctx.reply(f"Unlocked **{count}** text channels.")

@bot.command(name="mute")
async def mute(ctx, member: discord.Member = None, *, reason: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not member:
        return await ctx.reply("Usage: !mute @user [reason]")
    await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=10), reason=reason or "Muted by staff")
    await ctx.reply(f"Muted {member.mention} for 10 minutes" + (f" | Reason: {reason}" if reason else ""))

@bot.command(name="unmute")
async def unmute(ctx, member: discord.Member = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not member:
        return await ctx.reply("Usage: !unmute @user")
    await member.timeout(None)
    await ctx.reply(f"Unmuted {member.mention}")

@bot.command(name="kick")
async def kick(ctx, member: discord.Member = None, *, reason: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not member:
        return await ctx.reply("Usage: !kick @user [reason]")
    await member.kick(reason=reason)
    await ctx.reply(f"Kicked {member.mention}" + (f" | Reason: {reason}" if reason else ""))

@bot.command(name="ban")
async def ban(ctx, member: discord.Member = None, *, reason: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not member:
        return await ctx.reply("Usage: !ban @user [reason]")
    await member.ban(reason=reason)
    db = load_data()
    for uname, u in db.get("users", {}).items():
        if u.get("discord_id") == str(member.id):
            u["banned"] = True
            save_data(db)
            await ctx.reply(f"Banned {member.mention} | Reason: {reason or 'None'} | Flagged in Starware")
            return
    await ctx.reply(f"Banned {member.mention}" + (f" | Reason: {reason}" if reason else ""))

class BuyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Purchase", style=discord.ButtonStyle.green, emoji="\U0001f4b0", custom_id="buy_starware")
    async def buy_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower().replace(' ', '-')}")
        if existing:
            return await interaction.response.send_message(f"You already have a ticket: {existing.mention}", ephemeral=True)

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for uid in AUTHORIZED_USERS:
            member = guild.get_member(uid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower().replace(' ', '-')}",
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="Starware - Purchase Ticket",
            description=(
                "Thank you for your interest!\n\n"
                "To purchase Starware, please send your payment to the developer.\n"
                "Once payment is confirmed, you will receive your login credentials.\n\n"
                "**Available payment methods:**\n"
                "PayPal, Crypto (BTC/ETH), Gift Cards\n\n"
                "A staff member will be with you shortly."
            ),
            color=0xffd700
        )
        embed.set_footer(text="Starware | HWID-Locked Accounts")
        await channel.send(f"Welcome {user.mention}!", embed=embed)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

@bot.command(name="close")
async def close(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.reply("This is not a ticket channel.")
    allowed_ids = set(AUTHORIZED_USERS)
    allowed_ids.add(ctx.author.id)
    overwrites = ctx.channel.overwrites
    for target in overwrites:
        if isinstance(target, discord.Member) and target.id not in allowed_ids:
            overwrites[target] = discord.PermissionOverwrite(view_channel=False)
    await ctx.channel.edit(overwrites=overwrites)
    await ctx.send("Ticket closed. Only staff can see this now.")

@bot.command(name="delete")
async def delete(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.reply("This is not a ticket channel.")
    await ctx.send("Deleting ticket in 3 seconds...")
    await asyncio.sleep(3)
    await ctx.channel.delete()

@bot.command(name="setup")
async def setup(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    guild = ctx.guild
    msg = await ctx.reply("Setting up server...")

    buyer_role = discord.utils.get(guild.roles, name=BUYER_ROLE_NAME)
    if not buyer_role:
        buyer_role = await guild.create_role(name=BUYER_ROLE_NAME, color=0x00ff00)
        await msg.edit(content=f"Created `{BUYER_ROLE_NAME}` role")

    cat_names = [TICKET_CATEGORY_NAME, "Information", "Staff"]
    for name in cat_names:
        if not discord.utils.get(guild.categories, name=name):
            await guild.create_category(name)

    info_cat = discord.utils.get(guild.categories, name="Information")
    if info_cat:
        if not discord.utils.get(guild.text_channels, name="rules"):
            await guild.create_text_channel("rules", category=info_cat)
        if not discord.utils.get(guild.text_channels, name="announcements"):
            await guild.create_text_channel("announcements", category=info_cat)

    staff_cat = discord.utils.get(guild.categories, name="Staff")
    if staff_cat:
        if not discord.utils.get(guild.text_channels, name="staff-chat"):
            await guild.create_text_channel("staff-chat", category=staff_cat)

    await ctx.reply("Setup complete! Roles, categories, and channels created.")

@bot.command(name="testcmd")
async def testcmd(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    issues = []
    working = []
    for cmd in bot.commands:
        working.append(cmd.name)
        try:
            params = list(cmd.clean_params.keys()) if hasattr(cmd, 'clean_params') else []
        except:
            issues.append(f"`{cmd.name}` - failed to inspect params")
    if issues:
        embed = discord.Embed(title="Command Diagnostics - Issues Found", color=0xff0000)
        embed.add_field(name="Issues", value="\n".join(issues), inline=False)
    else:
        embed = discord.Embed(title="Command Diagnostics - All Clear", color=0x00ff00)
    embed.add_field(name=f"Registered Commands ({len(working)})", value=", ".join(f"`{w}`" for w in working), inline=False)
    try:
        load_data()
        embed.add_field(name="data.json", value="Loads OK", inline=True)
    except Exception as e:
        embed.add_field(name="data.json", value=f"Error: {e}", inline=True)
    try:
        app.url_map
        embed.add_field(name="Flask API", value=f"{len(app.url_map._rules)} routes", inline=True)
    except Exception as e:
        embed.add_field(name="Flask API", value=f"Error: {e}", inline=True)
    token_status = "Set via env" if os.environ.get("BOT_TOKEN") else "Placeholder (dev only)"
    embed.add_field(name="BOT_TOKEN", value=token_status, inline=True)
    embed.add_field(name="Master HWID", value=MASTER_HWID[:16] + "..." if MASTER_HWID != "unknown" else "unknown (Linux/Render)", inline=True)
    embed.add_field(name="Authorized Users", value=str(len(AUTHORIZED_USERS)), inline=True)
    embed.set_footer(text="Run !commands to see the full list")
    await ctx.reply(embed=embed)

@bot.command(name="testapi")
async def testapi(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.")
    try:
        import urllib.request
        base = f"http://localhost:{API_PORT}"
        resp = urllib.request.urlopen(f"{base}/ping", timeout=10)
        data = json.loads(resp.read())
        if data.get("status") == "ok":
            embed = discord.Embed(title="API Test - Local", color=0x00ff00)
            embed.add_field(name="Result", value="API is reachable locally")
            embed.add_field(name="Response", value=f"`{data['message']}`")
            embed.add_field(name="URL", value=f"`{base}/ping`")
        else:
            embed = discord.Embed(title="API Test - Local", color=0xff0000)
            embed.add_field(name="Result", value=f"Unexpected response: {data}")
    except Exception as e:
        embed = discord.Embed(title="API Test - Local", color=0xff0000)
        embed.add_field(name="Result", value=f"Local API unreachable: {e}")
    embed.add_field(name="Public URL", value="https://starware-bot.onrender.com/ping", inline=False)
    embed.add_field(name="Login Endpoint", value="POST https://starware-bot.onrender.com/login (username, password, hwid)", inline=False)
    embed.add_field(name="Check Endpoint", value="GET https://starware-bot.onrender.com/check?hwid=YOUR_HWID", inline=False)
    embed.set_footer(text="Configure Starware injector to use https://starware-bot.onrender.com")
    await ctx.reply(embed=embed)

@bot.command(name="myid")
async def myid(ctx):
    await ctx.reply(f"Your Discord ID: `{ctx.author.id}`")

@bot.command(name="commands")
async def commands_list(ctx):
    embed = discord.Embed(title="Starware Bot Commands", color=0xffd700)
    embed.add_field(name="Purchase & Accounts", value=(
        "`!panel` - Send the buy/support panel\n"
        "`!addbuyer @user username pass` - Create account + grant buyer role\n"
        "`!createuser username pass` - Create account only (no role)\n"
        "`!listusers` - List all accounts with HWID & sub status\n"
        "`!unbind username` - Reset HWID binding for an account\n"
        "`!stats [username]` - Overall summary or specific user's stats\n"
        "`!renew username` - Extend sub by 30 days\n"
        "`!extend username days` - Extend sub by custom days\n"
        "`!setlifetime [@user] <username>` - Grant lifetime access (optional @ for role)\n"
        "`!deleteuser username` - Delete a user account"
    ), inline=False)
    embed.add_field(name="Moderation", value=(
        "`!antiraid on/off` - Enable/disable raid auto-detection\n"
        "`!lockdown` - Lock all text channels\n"
        "`!unlock` - Unlock all text channels\n"
        "`!mute @user` - Mute a member (10 min timeout)\n"
        "`!unmute @user` - Unmute a member\n"
        "`!kick @user` - Kick a member from the server\n"
        "`!ban @user` - Ban a member (also flags in Starware)"
    ), inline=False)
    embed.add_field(name="Tickets", value=(
        "`!close` - Close the current ticket (ticket creator only)\n"
        "`!delete` - Delete the current ticket (admin only)"
    ), inline=False)
    embed.add_field(name="Server Setup", value=(
        "`!setup` - Auto-create roles, categories, channels, and permissions\n"
        "`!myid` - Get your Discord user ID\n"
        "`!commands` - Show this command list"
    ), inline=False)
    embed.add_field(name="Diagnostics", value=(
        "`!testcmd` - Check all bot commands for issues\n"
        "`!testapi` - Test the Flask API connectivity"
    ), inline=False)
    embed.set_footer(text="Starware")
    await ctx.reply(embed=embed)

def run_flask():
    app.run(host="0.0.0.0", port=API_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    if DATABASE_URL:
        init_db()
        print("Connected to PostgreSQL database")
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(BOT_TOKEN)
