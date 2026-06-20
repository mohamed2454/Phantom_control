import discord
from discord.ext import commands
from flask import Flask, render_template, request
import threading, asyncio, sqlite3, io, os, math, time, socket, aiohttp

# --- إعدادات التوكن ---
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN: TOKEN = TOKEN.strip().replace('"', '').replace("'", "")

MC_ROLES = ["Steve", "Alex", "Villager", "Zombie", "Creeper", "Enderman", "Skeleton", "Spider", "Piglin", "Ghast", 
            "Blaze", "Iron Golem", "Wither", "Ender Dragon", "Warden", "Herobrine", "Axolotl", "Bee", "Fox", "Wolf"]

# --- البوت المطور ---
class PhantomBot(commands.Bot):
    async def setup_hook(self):
        self.http.connector = aiohttp.TCPConnector(family=socket.AF_INET)
        self.add_view(TicketLaunch())
        self.add_view(TicketActions())

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = PhantomBot(command_prefix="!", intents=intents)

# --- قاعدة البيانات ---
DB_PATH = 'phantom_pro.db'
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS config (guild_id TEXT PRIMARY KEY, admin_roles TEXT, channel_id TEXT, log_channel TEXT, category_id TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS auto_replies (keyword TEXT, response TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS levels (user_id TEXT, xp INTEGER DEFAULT 0)')
    conn.commit() ; conn.close()
init_db()

# --- أنظمة التذاكر ---
class TicketActions(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="استلام ✋", style=discord.ButtonStyle.primary, custom_id="c_final")
    async def claim(self, i, b): await i.response.send_message(f"✅ استلم {i.user.mention} التذكرة.")
    @discord.ui.button(label="إغلاق 🔒", style=discord.ButtonStyle.danger, custom_id="l_final")
    async def close(self, i, b): await i.channel.delete()

class TicketLaunch(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="o_final")
    async def open(self, i, b):
        await i.response.defer(ephemeral=True)
        ch = await i.guild.create_text_channel(f"ticket-{i.user.name}")
        await i.followup.send(f"تم فتح تذكرتك: {ch.mention}", ephemeral=True)
        await ch.send(f"أهلاً {i.user.mention}", view=TicketActions())

# --- فعاليات البوت ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    conn = sqlite3.connect(DB_PATH)
    # الردود التلقائية
    r = conn.execute("SELECT response FROM auto_replies WHERE keyword=?", (message.content,)).fetchone()
    if r: await message.channel.send(r[0])
    # نظام الـ XP
    conn.execute("INSERT OR IGNORE INTO levels (user_id, xp) VALUES (?, 0)", (str(message.author.id),))
    conn.execute("UPDATE levels SET xp = xp + 1 WHERE user_id = ?", (str(message.author.id),))
    conn.commit(); conn.close()
    await bot.process_commands(message)

# --- لوحة التحكم (Flask) ---
app = Flask(__name__)
@app.route('/')
def home():
    status = "متصل ✅" if bot.is_ready() else "جاري فك الحظر... ⏳"
    g = bot.guilds[0] if bot.guilds else None
    ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
    tickets = len([c for c in bot.get_all_channels() if "ticket-" in c.name])
    return render_template('index.html', status=status, member_count=g.member_count if g else 0, ping=ping, open_tickets=tickets)

@app.route('/update_settings', methods=['POST'])
def update():
    f = request.form
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?, ?, ?, ?)", (f['guild_id'], f['admin_roles'], f['channel_id'], f['log_channel'], f['category_id']))
    conn.commit(); conn.close()
    asyncio.run_coroutine_threadsafe(bot.get_channel(int(f['channel_id'])).send("فتح تذكرة", view=TicketLaunch()), bot.loop)
    return "<h1>تم الحفظ!</h1><a href='/'>رجوع</a>"

@app.route('/add_auto_reply', methods=['POST'])
def add_reply():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO auto_replies VALUES (?, ?)", (request.form['keyword'], request.form['response']))
    conn.commit(); conn.close()
    return "<h1>تمت إضافة الرد!</h1><a href='/'>رجوع</a>"

@app.route('/broadcast', methods=['POST'])
def broadcast():
    gid, msg = request.form['guild_id'], request.form['msg']
    async def run_bdc():
        guild = bot.get_guild(int(gid))
        for m in guild.members:
            if not m.bot:
                try: await m.send(msg)
                except: continue
    asyncio.run_coroutine_threadsafe(run_bdc(), bot.loop)
    return "<h1>جاري إرسال البرودكاست...</h1><a href='/'>رجوع</a>"

@app.route('/create_mc_roles', methods=['POST'])
def mc_roles():
    gid = request.form['guild_id']
    async def make():
        g = bot.get_guild(int(gid))
        for r in MC_ROLES: await g.create_role(name=r, color=discord.Color.random())
    asyncio.run_coroutine_threadsafe(make(), bot.loop)
    return "<h1>جاري إنشاء الرتب...</h1><a href='/'>رجوع</a>"

@bot.event
async def on_ready(): print(f"--- ✅ {bot.user} متصل ---")

def run_web(): app.run(host='0.0.0.0', port=7860)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    while True:
        try: bot.run(TOKEN)
        except: time.sleep(60)
