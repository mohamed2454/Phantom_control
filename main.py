import discord
from discord.ext import commands
from flask import Flask, render_template, request
import threading, asyncio, sqlite3, io, os, math, time, socket, aiohttp

# --- 1. إعدادات التوكن ---
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN: TOKEN = TOKEN.strip().replace('"', '').replace("'", "")

# رتب ماين كرافت (20 رتبة)
MC_ROLES = ["Steve", "Alex", "Villager", "Zombie", "Creeper", "Enderman", "Skeleton", "Spider", "Piglin", "Ghast", 
            "Blaze", "Iron Golem", "Wither", "Ender Dragon", "Warden", "Herobrine", "Axolotl", "Bee", "Fox", "Wolf"]

# --- 2. تخصيص البوت (تجاوز الحظر وربط الأزرار) ---
class PhantomBot(commands.Bot):
    async def setup_hook(self):
        # إجبار الاتصال على IPv4 لتجنب حظر ديسكورد للسيرفرات المجانية
        self.http.connector = aiohttp.TCPConnector(family=socket.AF_INET)
        self.add_view(TicketLaunch())
        self.add_view(TicketActions())

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = PhantomBot(command_prefix="!", intents=intents)

# --- 3. قاعدة البيانات ---
DB_PATH = 'phantom_pro.db'
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS config (guild_id TEXT PRIMARY KEY, admin_roles TEXT, channel_id TEXT, log_channel TEXT, category_id TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS auto_replies (keyword TEXT, response TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS levels (user_id TEXT, xp INTEGER DEFAULT 0)')
    conn.commit() ; conn.close()
init_db()

# --- 4. أنظمة التذاكر ---
class TicketActions(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="استلام ✋", style=discord.ButtonStyle.primary, custom_id="claim_btn")
    async def claim(self, interaction, button):
        await interaction.response.send_message(f"✅ استلم {interaction.user.mention} التذكرة.")
    @discord.ui.button(label="إغلاق 🔒", style=discord.ButtonStyle.danger, custom_id="close_btn")
    async def close(self, interaction, button):
        await interaction.response.send_message("🔒 سيتم حذف القناة...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketLaunch(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="open_btn")
    async def open(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        # جلب الإعدادات
        conn = sqlite3.connect(DB_PATH)
        conf = conn.execute("SELECT admin_roles, category_id FROM config WHERE guild_id=?", (str(interaction.guild.id),)).fetchone()
        conn.close()
        
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                      interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                      interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        
        if conf and conf[0]:
            for r_id in conf[0].split(','):
                role = interaction.guild.get_role(int(r_id.strip()))
                if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        cat = interaction.guild.get_channel(int(conf[1])) if conf and conf[1] else None
        ch = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=cat)
        await interaction.followup.send(f"تم فتح تذكرتك: {ch.mention}", ephemeral=True)
        await ch.send(f"أهلاً {interaction.user.mention}", view=TicketActions())

# --- 5. نظام الـ XP والردود ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    conn = sqlite3.connect(DB_PATH)
    # ردود تلقائية
    r = conn.execute("SELECT response FROM auto_replies WHERE keyword=?", (message.content,)).fetchone()
    if r: await message.channel.send(r[0])
    # تلفيل
    conn.execute("INSERT OR IGNORE INTO levels (user_id, xp) VALUES (?, 0)", (str(message.author.id),))
    conn.execute("UPDATE levels SET xp = xp + 1 WHERE user_id = ?", (str(message.author.id),))
    conn.commit() ; conn.close()
    await bot.process_commands(message)

# --- 6. لوحة التحكم (Flask) ---
app = Flask(__name__)
@app.route('/')
def home():
    status = "متصل ✅" if bot.is_ready() else "جاري فك الحظر... ⏳"
    g = bot.guilds[0] if bot.guilds else None
    return render_template('index.html', status=status, bot_user=str(bot.user), 
                           guilds_count=len(bot.guilds), member_count=g.member_count if g else 0)

@app.route('/update_settings', methods=['POST'])
def update():
    f = request.form
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?, ?, ?, ?)", (f['guild_id'], f['admin_roles'], f['channel_id'], f['log_channel'], f['category_id']))
    conn.commit(); conn.close()
    ch = bot.get_channel(int(f['channel_id']))
    if ch: asyncio.run_coroutine_threadsafe(ch.send("فتح تذكرة", view=TicketLaunch()), bot.loop)
    return "<h1>تم الحفظ!</h1><a href='/'>رجوع</a>"

@app.route('/create_mc_roles', methods=['POST'])
def create_mc():
    gid = request.form['guild_id']
    guild = bot.get_guild(int(gid))
    if guild:
        async def make_roles():
            for r in MC_ROLES:
                if not discord.utils.get(guild.roles, name=r):
                    await guild.create_role(name=r, color=discord.Color.random())
        asyncio.run_coroutine_threadsafe(make_roles(), bot.loop)
    return "<h1>جاري الإنشاء...</h1><a href='/'>رجوع</a>"

# --- 7. التشغيل ---
def run_web(): app.run(host='0.0.0.0', port=7860)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    if TOKEN:
        while True:
            try: bot.run(TOKEN)
            except: time.sleep(120)
    else: print("Token Missing!")