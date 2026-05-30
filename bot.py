import os, discord
from discord.ext import commands, tasks
import json, hashlib, asyncio, subprocess
from pathlib import Path
import urllib.request as _ur
import ssl as _ssl

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set")
API_URL = "https://starware-api.onrender.com"
ADMIN_KEY = "starware-admin-2026"
AUTHORIZED_USERS = [1436458270759063603]
BUYER_ROLE_NAME = "Starware"
MEMBER_ROLE_NAME = "Star"
EXE_PATH = Path("/tmp/Star.exe")

_join_times = {}
_raid_mode = False
_nuke_protect = True
_invite_filter = True
_join_threshold = 5
_join_window = 10

def _wmic(query: str) -> str:
    try:
        r = subprocess.run(f'wmic {query}', capture_output=True, text=True, shell=True, timeout=3)
        lines = [l.strip() for l in r.stdout.split('\n') if l.strip()]
        return lines[-1] if lines else ''
    except:
        return ''

def get_hwid():
    try:
        parts = []
        disk = _wmic('diskdrive get serialnumber')
        if disk: parts.append(disk)
        mac = _wmic('nic where PhysicalAdapter=True get MACAddress')
        if mac: parts.append(mac)
        mb = _wmic('baseboard get serialnumber')
        if mb: parts.append(mb)
        vol = _wmic('volume get SerialNumber')
        if vol: parts.append(vol)
        raw = '-'.join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32] if raw else "unknown"
    except:
        return "unknown"

MASTER_HWID = get_hwid()

import time as _time

ACTIVE_WINDOW = 300
ROBLOX_VERSION_URL = "https://setup.roblox.com/version"
OFFSETS_URL = "https://offsets.imtheo.lol/offsets.json"
TYPES_URL = "https://offsets.imtheo.lol/types.json"
FFLAGS_URL = "https://offsets.imtheo.lol/fflags.json"
OFFSETS_DIR = Path("/tmp/offsets")
_last_roblox_version = None
_update_notified = False
_thursday_warned = False
_wednesday_warned = False

def _api_post(path: str, data: dict) -> dict | None:
    try:
        body = json.dumps(data).encode()
        req = _ur.Request(f"{API_URL}{path}", data=body, headers={
            "Content-Type": "application/json",
            "Authorization": ADMIN_KEY,
        })
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        resp = _ur.urlopen(req, timeout=10, context=ctx)
        return json.loads(resp.read().decode())
    except:
        return None

def _api_get(path: str) -> dict | None:
    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        resp = _ur.urlopen(f"{API_URL}{path}", timeout=10, context=ctx)
        return json.loads(resp.read().decode())
    except:
        return None

def _fetch_json(url: str, timeout: int = 10) -> dict | None:
    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        resp = _ur.urlopen(url, timeout=timeout, context=ctx)
        return json.loads(resp.read().decode())
    except:
        return None

def _check_remote_offsets() -> dict | None:
    data = _fetch_json(OFFSETS_URL)
    if not data:
        return None
    version = data.get("Roblox Version", "")
    offset_count = data.get("Total Offsets", 0)
    return {"version": version, "count": offset_count, "data": data}

@tasks.loop(minutes=2)
async def check_roblox_update():
    global _last_roblox_version, _update_notified, _wednesday_warned, _thursday_warned

    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        resp = _ur.urlopen(ROBLOX_VERSION_URL, timeout=10, context=ctx)
        current_version = resp.read().decode().strip()
    except:
        return

    now = _time.time()
    weekday = _time.gmtime(now).tm_wday

    if weekday == 2 and not _wednesday_warned:
        _wednesday_warned = True
        _thursday_warned = False
        for guild in bot.guilds:
            ch = discord.utils.get(guild.text_channels, name="updates") or discord.utils.get(guild.text_channels, name="announcements")
            if ch:
                await ch.send(f"\U0001f4c5 **Reminder:** Roblox typically updates **tomorrow (Thursday)**. Expect injector downtime after.")
                break
    elif weekday == 3 and not _thursday_warned:
        _thursday_warned = True
        _wednesday_warned = False
        for guild in bot.guilds:
            ch = discord.utils.get(guild.text_channels, name="updates") or discord.utils.get(guild.text_channels, name="announcements")
            if ch:
                await ch.send(f"\u26a0\ufe0f **Roblox update expected today!** Offsets may break. I'll auto-update once ready.")
                break
    else:
        _wednesday_warned = False
        _thursday_warned = False

    if _last_roblox_version is None:
        _last_roblox_version = current_version
        return

    if current_version != _last_roblox_version:
        _last_roblox_version = current_version
        _update_notified = False
        for guild in bot.guilds:
            ch = discord.utils.get(guild.text_channels, name="updates") or discord.utils.get(guild.text_channels, name="announcements")
            if ch:
                await ch.send(
                    f"\u26a0\ufe0f **Roblox Just Updated!**\n"
                    f"New Version: `{current_version}`\n"
                    f"\U0001f504 Injector may not work until offsets refresh.\n"
                    f"\U0001f4e6 Waiting for offsets.imtheo.lol to update..."
                )
                break
        return

    if _update_notified:
        return

    info = _check_remote_offsets()
    if not info or info["version"] != current_version:
        return

    types = _fetch_json(TYPES_URL)
    fflags = _fetch_json(FFLAGS_URL)
    OFFSETS_DIR.mkdir(parents=True, exist_ok=True)
    (OFFSETS_DIR / "offsets.json").write_text(json.dumps(info["data"], indent=2))
    if types:
        (OFFSETS_DIR / "types.json").write_text(json.dumps(types, indent=2))
    if fflags:
        (OFFSETS_DIR / "fflags.json").write_text(json.dumps(fflags, indent=2))
    _update_notified = True
    for guild in bot.guilds:
        ch = discord.utils.get(guild.text_channels, name="updates") or discord.utils.get(guild.text_channels, name="announcements")
        if ch:
            await ch.send(
                f"\u2705 **Offsets Updated!**\n"
                f"Version: `{current_version}`\n"
                f"Offsets: `{info['count']}`\n"
                f"\U0001f4e6 Auto-downloaded. Restart the injector to apply."
            )
            break

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

TICKET_CATEGORY_NAME = "\U0001f3ab TICKETS"

async def _ephemeral_reply(ctx, *args, **kwargs):
    kwargs.setdefault("delete_after", 10)
    return await ctx.reply(*args, **kwargs)

class BuyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _create_ticket(self, interaction: discord.Interaction, ticket_type: str, title: str, message: str):
        guild = interaction.guild
        user = interaction.user
        prefix = "support" if ticket_type == "support" else "ticket"
        existing_name = f"{prefix}-{user.name.lower().replace(' ', '-')}"

        existing = discord.utils.get(guild.text_channels, name=existing_name)
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

        channel = await guild.create_text_channel(name=existing_name, category=category, overwrites=overwrites)

        embed = discord.Embed(title=title, description=message, color=0xffd700)
        embed.set_footer(text="Starware \u2b50")
        await channel.send(f"Welcome {user.mention}!", embed=embed)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

    @discord.ui.button(label="Purchase", style=discord.ButtonStyle.green, emoji="\U0001f4b0", custom_id="buy_starware")
    async def buy_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._create_ticket(
            interaction, "purchase",
            "\u2b50 Starware \u2014 Purchase Ticket",
            (
                f"Thank you for your interest!\n\n"
                f"\U0001f4b3 Send your payment in this ticket.\n"
                f"Once confirmed, you'll receive your login credentials and instant access.\n\n"
                f"\u2728 **Accepted payments:**\n"
                f"\u2022 PayPal\n\u2022 Fruits (Blox Fruits / GP)"
            )
        )

    @discord.ui.button(label="Support", style=discord.ButtonStyle.blurple, emoji="\U0001f6e0\ufe0f", custom_id="support_starware")
    async def support_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._create_ticket(
            interaction, "support",
            "\U0001f6e0\ufe0f Starware \u2014 Support Ticket",
            (
                f"Please describe your issue in detail.\n"
                f"A staff member will assist you as soon as possible.\n\n"
                f"**Common topics:**\n"
                f"\u2022 Login issues\n\u2022 HWID problems\n\u2022 General help"
            )
        )

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    print(f"Master HWID: {MASTER_HWID}")
    try:
        bot.add_view(BuyView())
    except Exception:
        pass
    check_roblox_update.start()

@bot.event
async def on_member_join(member: discord.Member):
    global _join_times, _raid_mode
    member_role = discord.utils.get(member.guild.roles, name=MEMBER_ROLE_NAME)
    if member_role:
        try:
            await member.add_roles(member_role)
        except:
            pass
    now = discord.utils.utcnow().timestamp()
    guild_id = member.guild.id
    if guild_id not in _join_times:
        _join_times[guild_id] = []
    _join_times[guild_id].append(now)
    cutoff = now - _join_window
    _join_times[guild_id] = [t for t in _join_times[guild_id] if t > cutoff]
    if len(_join_times[guild_id]) >= _join_threshold and not _raid_mode:
        _raid_mode = True
        guild = member.guild
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                await ch.send(f"\u26a0\ufe0f **Raid detected!** Locking down the server. New members cannot speak until reviewed.")
                break
        role = discord.utils.get(guild.roles, name="Muted")
        if role is None:
            role = await guild.create_role(name="Muted", colour=discord.Colour.dark_red())
            for ch in guild.channels:
                await ch.set_permissions(role, send_messages=False, add_reactions=False, speak=False)
        for ch in guild.text_channels:
            await ch.set_permissions(guild.default_role, send_messages=False)
        await asyncio.sleep(120)
        _raid_mode = False
        for ch in guild.text_channels:
            await ch.set_permissions(guild.default_role, send_messages=None)
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                await ch.send("\u2705 Server lockdown lifted. Raid has passed.")

@bot.event
async def on_guild_channel_delete(channel):
    if not _nuke_protect:
        return
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        deleter = entry.user
        if deleter.id not in AUTHORIZED_USERS and not deleter.bot:
            try:
                await guild.ban(deleter, reason="Nuke protection: mass channel deletion")
            except:
                pass
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    await ch.send(f"\u26a0\ufe0f **Nuke attempt blocked!** Banned {deleter.mention} for deleting channels.")
                    break
        break

@bot.event
async def on_message(msg):
    await bot.process_commands(msg)
    if msg.author.bot or not _invite_filter:
        return
    guild = msg.guild
    if not guild or msg.author.id in AUTHORIZED_USERS:
        return
    if "discord.gg/" in msg.content or "discord.com/invite/" in msg.content:
        await msg.delete()
        await msg.channel.send(f"{msg.author.mention} No advertising allowed.", delete_after=3)

@bot.command(name="panel")
async def panel(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    embed = discord.Embed(
        title="\u2b50 Starware \u2014 Purchase Access",
        description=(
            "Click **Purchase** to buy access or **Support** for help.\n"
            "A private ticket will be opened for you.\n\n"
            "\u2022 **HWID-Locked** \u2014 one device per account\n"
            "\u2022 **\u20ac5/month** via PayPal or **\u20ac35 lifetime**\n"
            "\u2022 **Instant delivery** after payment\n\n"
            "\u2728 **Accepted payments:** PayPal, Fruits"
        ),
        color=0xffd700
    )
    embed.set_footer(text="Starware | The ultimate Roblox injector \u2b50")
    await ctx.send(embed=embed, view=BuyView())

@bot.command(name="createuser")
async def createuser(ctx, username: str, password: str):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    username = username.strip().lower()
    if not username or not password:
        return await ctx.reply("Usage: !createuser <username> <password>")
    data = _api_post("/admin/create", {"username": username, "password": password, "created_by": ctx.author.name})
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, data.get("message", "API error") if data else "API unreachable")
    await _ephemeral_reply(ctx, f"User `{username}` created successfully! (30 days subscription)")

@bot.command(name="listusers")
async def listusers(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    data = _api_get("/admin/users")
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, "Failed to fetch users.")
    users = data.get("users", {})
    if not users:
        return await ctx.reply("No users.")
    lines = []
    for uname, u in users.items():
        hwid_status = f"bound ({u['hwid'][:12]}...)" if u.get("hwid") else "unbound"
        expiry = u.get("sub_expiry")
        if expiry:
            remaining = expiry - _time.time()
            if remaining > 0:
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                time_str = f"{days}d {hours}h"
            else:
                time_str = "EXPIRED"
        else:
            time_str = "lifetime"
        lines.append(f"**{uname}** \u2014 {hwid_status} \u2014 {time_str}")
    await _ephemeral_reply(ctx, "\n".join(lines))

@bot.command(name="unbind")
async def unbind(ctx, username: str):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    username = username.strip().lower()
    data = _api_post("/admin/unbind", {"username": username})
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, data.get("message", "API error") if data else "API unreachable")
    await _ephemeral_reply(ctx, f"Unbound `{username}` from their HWID.")

@bot.command(name="stats")
async def stats(ctx, username: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    data = _api_get("/admin/users")
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, "Failed to fetch users.")
    users = data.get("users", {})

    if username:
        username = username.strip().lower()
        user = users.get(username)
        if not user:
            return await ctx.reply("User not found.")
        hwid = user.get("hwid", None)
        bound = f"`{hwid[:16]}...`" if hwid else "Not bound"
        expiry = user.get("sub_expiry")
        now = _time.time()
        if expiry is None:
            sub_status = "\U0001f525 **Lifetime**"
        elif expiry > now:
            days = int((expiry - now) // 86400)
            sub_status = f"\U0001f4c5 **{days} days remaining** (<t:{int(expiry)}:R>)"
        else:
            sub_status = "\u274c **Expired**"
        embed = discord.Embed(title=f"\u2b50 Stats: `{username}`", color=0xffd700)
        embed.add_field(name="HWID", value=bound)
        embed.add_field(name="Subscription", value=sub_status)
        embed.add_field(name="Created By", value=user.get("created_by", "?"))
        return await _ephemeral_reply(ctx, embed=embed)

    total = len(users)
    bound = sum(1 for u in users.values() if u.get("hwid"))
    now = _time.time()
    lifetime = sum(1 for u in users.values() if u.get("sub_expiry") is None)
    active_monthly = sum(1 for u in users.values() if u.get("sub_expiry") is not None and u["sub_expiry"] > now)
    expired = total - lifetime - active_monthly
    embed = discord.Embed(title="Star Account Stats", color=0xffd700)
    embed.add_field(name="Total Accounts", value=str(total))
    embed.add_field(name="HWID-Bound", value=str(bound))
    embed.add_field(name="Unbound", value=str(total - bound))
    embed.add_field(name="\U0001f525 Lifetime", value=str(lifetime))
    embed.add_field(name="\U0001f4c5 Monthly", value=str(active_monthly))
    embed.add_field(name="\u274c Expired", value=str(expired))
    await _ephemeral_reply(ctx, embed=embed)

@bot.command(name="addbuyer")
async def addbuyer(ctx, member: discord.Member, username: str, password: str):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)

    username = username.strip().lower()
    data = _api_post("/admin/create", {"username": username, "password": password, "created_by": ctx.author.name})
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, data.get("message", "API error") if data else "API unreachable")

    role = discord.utils.get(ctx.guild.roles, name=BUYER_ROLE_NAME)
    if role is None:
        role = await ctx.guild.create_role(name=BUYER_ROLE_NAME, colour=discord.Colour.gold())

    await member.add_roles(role)
    embed = discord.Embed(
        title="\u2b50 Starware Access Granted",
        description=(
            f"{member.mention} has been granted **{BUYER_ROLE_NAME}** access!\n\n"
            f"\U0001f464 **Username:** `{username}`\n"
            f"\U0001f511 **Password:** `{password}`\n"
            f"\U0001f510 **HWID:** Not bound yet (binds on first login)\n"
            f"\U0001f4c5 **Subscription:** 30 days (renew via PayPal \u20ac5/month)\n\n"
            "They can now access the buyers channels."
        ),
        color=0xffd700
    )
    embed.set_footer(text="Starware | Login credentials \u2b50")
    await ctx.reply(embed=embed)
    if EXE_PATH.exists():
        await ctx.send(f"{member.mention} \u2b50 Here is your download:", file=discord.File(str(EXE_PATH)))

@bot.command(name="renew")
async def renew(ctx, username: str):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    username = username.strip().lower()
    data = _api_post("/admin/renew", {"username": username})
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, data.get("message", "API error") if data else "API unreachable")
    await _ephemeral_reply(ctx, f"Renewed `{username}` for another 30 days. Expires: <t:{int(data['expiry'])}:R>")

@bot.command(name="extend")
async def extend(ctx, username: str, days: int):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    username = username.strip().lower()
    data = _api_post("/admin/extend", {"username": username, "days": days})
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, data.get("message", "API error") if data else "API unreachable")
    await _ephemeral_reply(ctx, f"Extended `{username}` by {days} days. Expires: <t:{int(data['expiry'])}:R>")

@bot.command(name="setlifetime")
async def setlifetime(ctx, username: str):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    username = username.strip().lower()
    data = _api_post("/admin/setlifetime", {"username": username})
    if not data or data.get("status") != "ok":
        return await _ephemeral_reply(ctx, data.get("message", "API error") if data else "API unreachable")
    await _ephemeral_reply(ctx, f"`{username}` now has **lifetime** access!")

@bot.command(name="setup")
async def setup(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)

    msg = await ctx.reply("\u2b50 Setting up your server...")

    role = discord.utils.get(ctx.guild.roles, name=BUYER_ROLE_NAME)
    if role is None:
        role = await ctx.guild.create_role(name=BUYER_ROLE_NAME, colour=discord.Colour.gold(), hoist=True)
        await msg.edit(content=f"{role.mention} role created!")

    member_role = discord.utils.get(ctx.guild.roles, name=MEMBER_ROLE_NAME)
    if member_role is None:
        member_role = await ctx.guild.create_role(name=MEMBER_ROLE_NAME, colour=discord.Colour.from_str("#5865F2"))
        await msg.edit(content=f"{member_role.mention} member role created!")

    buyer_cat = discord.utils.get(ctx.guild.categories, name="\u2b50 STARWARE")
    if buyer_cat is None:
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        buyer_cat = await ctx.guild.create_category("\u2b50 STARWARE", overwrites=overwrites)
        await msg.edit(content=f"{buyer_cat.name} category created!")

    for ch_data in [
        ("changelogs", "Latest patch notes and version history will be posted here.", True),
        ("updates", "\U0001f6a8 Roblox update notifications will be posted here automatically.", True),
        ("buyers-chat", f"Buyers discussion {role.mention}. Chat about anything!", False),
        ("media", f"Share your clips, screenshots, and media {role.mention}.", False),
    ]:
        if not discord.utils.get(ctx.guild.text_channels, name=ch_data[0], category=buyer_cat):
            ch = await ctx.guild.create_text_channel(ch_data[0], category=buyer_cat)
            await ch.send(ch_data[1])
            await msg.edit(content=f"#{ch.name} channel created!")

    if not discord.utils.get(ctx.guild.voice_channels, name="Voice Chat", category=buyer_cat):
        vc = await ctx.guild.create_voice_channel("Voice Chat", category=buyer_cat)
        await msg.edit(content=f"#{vc.name} voice channel created!")

    panel_cat = discord.utils.get(ctx.guild.categories, name="\u2728 PURCHASE STARWARE")
    if panel_cat is None:
        panel_cat = await ctx.guild.create_category("\u2728 PURCHASE STARWARE")
        await msg.edit(content=f"{panel_cat.name} category created!")

    if not discord.utils.get(ctx.guild.text_channels, name="buy-here", category=panel_cat):
        ch = await ctx.guild.create_text_channel("buy-here", category=panel_cat)
    await msg.edit(content=f"#buy-here channel ready!")

    if not discord.utils.get(ctx.guild.text_channels, name="info", category=panel_cat):
        ch = await ctx.guild.create_text_channel("info", category=panel_cat)
    await msg.edit(content=f"#info channel ready!")

    public_cat = discord.utils.get(ctx.guild.categories, name="\U0001f30d COMMUNITY")
    if public_cat is None:
        public_cat = await ctx.guild.create_category("\U0001f30d COMMUNITY")
        await msg.edit(content=f"{public_cat.name} category created!")

    if not discord.utils.get(ctx.guild.text_channels, name="general", category=public_cat):
        ch = await ctx.guild.create_text_channel("general", category=public_cat)
        await ch.send("Welcome! Feel free to chat here.")
    await msg.edit(content=f"#general channel ready!")

    if not discord.utils.get(ctx.guild.text_channels, name="announcements", category=public_cat):
        ch = await ctx.guild.create_text_channel("announcements", category=public_cat)
    await msg.edit(content=f"#announcements channel ready!")

    if not discord.utils.get(ctx.guild.text_channels, name="rules", category=public_cat):
        ch = await ctx.guild.create_text_channel("rules", category=public_cat)
    await msg.edit(content=f"#rules channel ready!")

    read_only_names = {"announcements", "rules", "changelogs", "buy-here", "info", "updates"}
    for cat in (public_cat, buyer_cat, panel_cat):
        if cat is None:
            continue
        for ch in cat.text_channels:
            if ch.name in read_only_names:
                await ch.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)
                for uid in AUTHORIZED_USERS:
                    m = ctx.guild.get_member(uid)
                    if m:
                        await ch.set_permissions(m, send_messages=True)

    ch = discord.utils.get(ctx.guild.text_channels, name="announcements", category=public_cat)
    if ch:
        await ch.send("Welcome to **Starware**! Official announcements will be posted here.")

    ch = discord.utils.get(ctx.guild.text_channels, name="changelogs", category=buyer_cat)
    if ch:
        await ch.send("Latest patch notes and version history will be posted here.")

    ch = discord.utils.get(ctx.guild.text_channels, name="buy-here", category=panel_cat)
    if ch:
        await ch.send(
            content=f"{role.mention} \u2b50",
            embed=discord.Embed(
                title="\u2b50 Starware \u2014 Purchase Access",
                description=(
                    "Click **Purchase** to buy access or **Support** for help.\n"
                    "A private ticket will be opened for you.\n\n"
                    "\u2022 **HWID-Locked** \u2014 one device per account\n"
                    "\u2022 **\u20ac5/month** via PayPal or **\u20ac35 lifetime**\n"
                    "\u2022 **Instant delivery** after payment\n\n"
                    "\u2728 **Accepted payments:** PayPal, Fruits"
                ),
                color=0xffd700
            ).set_footer(text="Starware | The ultimate Roblox injector"),
            view=BuyView()
        )

    ch = discord.utils.get(ctx.guild.text_channels, name="info", category=panel_cat)
    if ch:
        await ch.send(
            content=f"{role.mention} \u2b50",
            embed=discord.Embed(
                title="\u2139\ufe0f About Starware",
                description=(
                    "Starware is the ultimate Roblox injector.\n\n"
                    "\u2022 **HWID-Locked** \u2014 one device per account\n"
                    "\u2022 **\u20ac5/month** or **\u20ac35 lifetime**\n"
                    "\u2022 **Instant delivery** after payment\n\n"
                    "Check **#rules** in the Community category for server rules."
                ),
                color=0xffd700
            )
        )

    ch = discord.utils.get(ctx.guild.text_channels, name="rules", category=public_cat)
    if ch:
        rules_embed = discord.Embed(
            title="\u2b50 Starware Server Rules",
            description=(
                "**1. Be respectful** \u2014 No harassment, hate speech, or toxicity.\n"
                "**2. No advertising** \u2014 No self-promotion or DMs selling stuff.\n"
                "**3. No spam** \u2014 Keep channels clean and on-topic.\n"
                "**4. Follow Discord TOS** \u2014 You must be 13+ to be here.\n"
                "**5. No refunds** \u2014 All purchases are final.\n"
                "**6. Staff decisions are final.**\n\n"
                "\u26a0\ufe0f **Disclaimer:**\n"
                "Starware is a third-party tool **not affiliated with Roblox Corporation**.\n"
                "Roblox\u00ae is a registered trademark of Roblox Corporation.\n"
                "This software is for **educational purposes only**.\n"
                "Use at your own risk. We are not responsible for any actions taken against your account.\n"
                "By using Starware, you agree that you understand the risks involved with third-party tools."
            ),
            color=0xffd700
        )
        rules_embed.set_footer(text="Starware | Not affiliated with Roblox Corporation")
        await ch.send(embed=rules_embed)

    await msg.edit(content="\u2705 **Server setup complete!** \u2b50\nTickets category is created automatically when someone opens a ticket.")

@bot.command(name="commands")
async def cmd_list(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    embed = discord.Embed(title="\u2b50 Starware Bot Commands", color=0xffd700)
    embed.add_field(name="\U0001f4b0 Purchase & Accounts",
        value="`!panel` - Send the buy/support panel\n"
              "`!addbuyer @user username pass` - Create account + grant buyer role\n"
              "`!createuser username pass` - Create account only (no role)\n"
              "`!listusers` - List all accounts with HWID & sub status\n"
              "`!unbind username` - Reset HWID binding for an account\n"
              "`!stats` - Overall account summary\n"
              "`!stats username` - Show specific user's stats\n"
              "`!renew username` - Extend sub by 30 days (\u20ac5)\n"
              "`!extend username days` - Extend sub by custom days\n"
              "`!setlifetime username` - Grant lifetime access (\u20ac35)",
        inline=False)
    embed.add_field(name="\U0001f6e0\ufe0f Moderation",
        value="`!antiraid on/off` - Enable/disable raid auto-detection\n"
              "`!lockdown` - Lock all text channels (@everyone can't send)\n"
              "`!unlock` - Unlock all text channels\n"
              "`!mute @user` - Mute a member (prevents typing)\n"
              "`!unmute @user` - Unmute a member\n"
              "`!kick @user` - Kick a member from the server\n"
              "`!ban @user` - Ban a member from the server",
        inline=False)
    embed.add_field(name="\U0001f3ab Tickets",
        value="`!close` - Close the current ticket (ticket creator only)\n"
              "`!delete` - Delete the current ticket (admin only)",
        inline=False)
    embed.add_field(name="\u2699\ufe0f Server Setup",
        value="`!setup` - Auto-create roles, categories, channels, and permissions\n"
              "`!adminpanel` - Create private admin channel with all user info\n"
              "`!adminrefresh` - Refresh the admin panel embed\n"
              "`!online` - Show currently online users\n"
              "`!checkupdate` - Check Roblox version and force offset update\n"
              "`!myid` - Get your Discord user ID\n"
              "`!commands` - Show this command list",
        inline=False)
    embed.set_footer(text="Starware \u2b50")
    await ctx.send(embed=embed, delete_after=10)

@bot.command(name="adminpanel")
async def adminpanel(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", delete_after=10)
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    existing = discord.utils.get(ctx.guild.text_channels, name="admin-panel")
    if existing:
        await existing.delete()
    channel = await ctx.guild.create_text_channel("admin-panel", overwrites=overwrites)
    await channel.send(embed=_build_admin_embed())
    await ctx.reply(f"Admin panel created: {channel.mention}", delete_after=10)

def _build_admin_embed():
    data = _api_get("/admin/users")
    users = (data or {}).get("users", {})
    embed = discord.Embed(title="\u2b50 Starware Admin Panel", color=0xffd700)
    embed.set_footer(text=f"Updated: <t:{int(_time.time())}:T>")
    if not users:
        embed.description = "No users registered."
        return embed
    now = _time.time()
    cutoff = now - ACTIVE_WINDOW
    for uname, u in users.items():
        hwid = u.get("hwid", "N/A")
        hwid_short = f"`{hwid[:16]}...`" if hwid and hwid != "N/A" else "Not bound"
        expiry = u.get("sub_expiry")
        last = u.get("last_active")
        online = "\U0001f7e2 Online" if last and last > cutoff else "\u26aa Offline"
        if expiry is None:
            sub = "\U0001f525 Lifetime"
        elif expiry > now:
            days = int((expiry - now) // 86400)
            sub = f"\U0001f4c5 {days}d left (<t:{int(expiry)}:R>)"
        else:
            sub = "\u274c Expired"
        embed.add_field(
            name=f"\U0001f464 {uname} {online}",
            value=f"Pass: `{u.get('password_plain', '?')[:20]}`\n"
                  f"HWID: {hwid_short}\n"
                  f"Sub: {sub}",
            inline=True
        )
    return embed

@bot.command(name="adminrefresh")
async def adminrefresh(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", delete_after=10)
    ch = discord.utils.get(ctx.guild.text_channels, name="admin-panel")
    if not ch:
        return await ctx.reply("No admin-panel channel found. Run `!adminpanel` first.", delete_after=10)
    await ctx.message.delete()
    async for msg in ch.history(limit=10):
        if msg.author == bot.user:
            await msg.edit(embed=_build_admin_embed())
            break
    else:
        await ch.send(embed=_build_admin_embed())

@bot.command(name="online")
async def online(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", delete_after=10)
    try:
        resp = _ur.urlopen(f"{API_URL}/active", timeout=5)
        data = json.loads(resp.read().decode())
    except:
        return await _ephemeral_reply(ctx, "Failed to fetch active users.")
    online_users = data.get("users", [])
    if not online_users:
        return await _ephemeral_reply(ctx, "\u26aa No users currently online.")
    lines = [f"\U0001f7e2 **{u['username']}** - HWID: `{u['hwid']}` - Last seen: <t:{int(u['last_seen'])}:R>" for u in online_users]
    await _ephemeral_reply(ctx, "\n".join(lines))

@bot.command(name="checkupdate")
async def checkupdate(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", delete_after=10)
    global _last_roblox_version
    info = _check_remote_offsets()
    if not info:
        return await _ephemeral_reply(ctx, "Failed to fetch remote offsets.")
    current_local = None
    local_file = OFFSETS_DIR / "offsets.json"
    if local_file.exists():
        try:
            current_local = json.loads(local_file.read_text()).get("Roblox Version", "unknown")
        except:
            current_local = "unknown"
    embed = discord.Embed(title="\U0001f6a8 Roblox Update Check", color=0xffd700)
    embed.add_field(name="Current Remote", value=f"`{info['version']}` ({info['count']} offsets)")
    embed.add_field(name="Local Stored", value=f"`{current_local}`" if current_local else "No local data")
    embed.add_field(name="Auto-Updates", value="Every 5 minutes" if check_roblox_update.is_running() else "Stopped")
    if current_local and info["version"] != current_local:
        embed.description = "\u26a0\ufe0f **Update available!** Auto-downloading now..."
        _last_roblox_version = current_local
        await check_roblox_update()
    await _ephemeral_reply(ctx, embed=embed)

@bot.command(name="myid")
async def myid(ctx):
    try:
        await ctx.author.send(f"Your Discord ID: `{ctx.author.id}`")
        try:
            await ctx.message.delete()
        except:
            pass
    except:
        await ctx.reply(f"Your Discord ID: `{ctx.author.id}`")

@bot.command(name="close")
async def close(ctx):
    if not ctx.channel.name.startswith(("ticket-", "support-")):
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
        return await ctx.reply("Not authorized.", ephemeral=True)
    if not ctx.channel.name.startswith(("ticket-", "support-")):
        return await ctx.reply("This is not a ticket channel.")
    await ctx.send("Deleting ticket in 3 seconds...")
    await asyncio.sleep(3)
    await ctx.channel.delete()

@bot.command(name="antiraid")
async def antiraid(ctx, mode: str = None):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    global _raid_mode
    if mode == "on":
        for ch in ctx.guild.text_channels:
            await ch.set_permissions(ctx.guild.default_role, send_messages=False)
        _raid_mode = True
        await _ephemeral_reply(ctx, "\u26a0\ufe0f **Manual raid mode enabled.** Everyone muted.")
    elif mode == "off":
        for ch in ctx.guild.text_channels:
            await ch.set_permissions(ctx.guild.default_role, send_messages=None)
        _raid_mode = False
        await _ephemeral_reply(ctx, "\u2705 **Raid mode disabled.**")
    else:
        await _ephemeral_reply(ctx, f"Usage: `!antiraid on` or `!antiraid off`\nCurrent status: {'ON' if _raid_mode else 'OFF'}")

@bot.command(name="lockdown")
async def lockdown(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    for ch in ctx.guild.text_channels:
        await ch.set_permissions(ctx.guild.default_role, send_messages=False)
    await _ephemeral_reply(ctx, "\u26a0\ufe0f **Server locked down.** Only staff can speak.")

@bot.command(name="unlock")
async def unlock(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    for ch in ctx.guild.text_channels:
        await ch.set_permissions(ctx.guild.default_role, send_messages=None)
    await _ephemeral_reply(ctx, "\u2705 **Server unlocked.**")

@bot.command(name="mute")
async def mute(ctx, member: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if role is None:
        role = await ctx.guild.create_role(name="Muted", colour=discord.Colour.dark_red())
        for ch in ctx.guild.channels:
            await ch.set_permissions(role, send_messages=False, add_reactions=False, speak=False)
    await member.add_roles(role)
    await _ephemeral_reply(ctx, f"\u2705 Muted {member.mention}.")

@bot.command(name="unmute")
async def unmute(ctx, member: discord.Member):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if role and role in member.roles:
        await member.remove_roles(role)
    await _ephemeral_reply(ctx, f"\u2705 Unmuted {member.mention}.")

@bot.command(name="ban")
async def ban_user(ctx, member: discord.Member, *, reason: str = "No reason"):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    await member.ban(reason=reason)
    await _ephemeral_reply(ctx, f"\u26d4 Banned {member.mention}. Reason: {reason}")

@bot.command(name="kick")
async def kick_user(ctx, member: discord.Member, *, reason: str = "No reason"):
    if ctx.author.id not in AUTHORIZED_USERS:
        return await ctx.reply("Not authorized.", ephemeral=True)
    await member.kick(reason=reason)
    await _ephemeral_reply(ctx, f"\U0001f4a2 Kicked {member.mention}. Reason: {reason}")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
