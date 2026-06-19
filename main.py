import discord
from discord.ext import commands
from flask import Flask, render_template, request
import threading, asyncio, sqlite3, io

# --- الإعدادات الأساسية ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

MC_ROLES = ["Steve", "Alex", "Villager", "Zombie", "Creeper", "Enderman", "Skeleton", "Spider", "Piglin", "Ghast", 
            "Blaze", "Iron Golem", "Wither", "Ender Dragon", "Warden", "Herobrine", "Axolotl", "Bee", "Fox", "Wolf"]

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('phantom_pro.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS config 
                 (guild_id TEXT PRIMARY KEY, admin_roles TEXT, channel_id TEXT, log_channel TEXT, category_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS auto_replies (keyword TEXT, response TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS levels (user_id TEXT, xp INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def get_config(guild_id):
    conn = sqlite3.connect('phantom_pro.db')
    res = conn.execute("SELECT admin_roles, channel_id, log_channel, category_id FROM config WHERE guild_id=?", (str(guild_id),)).fetchone()
    conn.close()
    return res

# --- نظام التذاكر ---
class TicketActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام التذكرة ✋", style=discord.ButtonStyle.primary, custom_id="claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send(f"✅ تم استلام التذكرة بواسطة {interaction.user.mention}")
        button.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="إغلاق وأرشفة 🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # إنشاء الأرشيف
        buffer = io.BytesIO()
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            buffer.write(f"{message.created_at} - {message.author}: {message.content}\n".encode())
        buffer.seek(0)
        file = discord.File(buffer, filename=f"archive-{interaction.channel.name}.txt")

        config = get_config(interaction.guild.id)
        if config and config[2]:
            log_ch = bot.get_channel(int(config[2]))
            if log_ch: await log_ch.send(f"🔒 تذكرة مغلقة: `{interaction.channel.name}`\nبواسطة: {interaction.user}", file=file)

        await interaction.followup.send("سيتم حذف القناة خلال ثوانٍ...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketLaunch(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="open")
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        config = get_config(interaction.guild.id)
        if not config: return await interaction.followup.send("يجب ضبط الإعدادات من الموقع أولاً!")

        admin_ids = config[0].split(',')
        category_id = config[3]
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for r_id in admin_ids:
            role = interaction.guild.get_role(int(r_id.strip()))
            if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        cat = interaction.guild.get_channel(int(category_id)) if category_id else None
        channel = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=cat)
        
        await interaction.followup.send(f"تم فتح تذكرتك: {channel.mention}", ephemeral=True)
        await channel.send(f"مرحباً {interaction.user.mention}، سيتم الرد عليك من قبل الإدارة.", view=TicketActions())

# --- نظام الرسائل والرتب ---
@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. الردود التلقائية
    conn = sqlite3.connect('phantom_pro.db')
    res = conn.execute("SELECT response FROM auto_replies WHERE keyword=?", (message.content,)).fetchone()
    if res: await message.channel.send(res[0])

    # 2. الـ XP والرتب التلقائية
    uid = str(message.author.id)
    conn.execute("INSERT OR IGNORE INTO levels VALUES (?, 0)", (uid,))
    conn.execute("UPDATE levels SET xp = xp + 1 WHERE user_id = ?", (uid,))
    xp = conn.execute("SELECT xp FROM levels WHERE user_id = ?", (uid,)).fetchone()[0]
    conn.commit()
    conn.close()

    if xp % 50 == 0: # ترقية كل 50 رسالة
        idx = min(xp // 50, len(MC_ROLES)-1)
        role = discord.utils.get(message.guild.roles, name=MC_ROLES[idx])
        if role: await message.author.add_roles(role)

    # 3. أمر إعطاء رتبة مخصص (+اسم_الرتبة @عضو)
    if message.content.startswith("+"):
        parts = message.content.split()
        if len(parts) >= 2 and message.mentions:
            r_name = parts[0][1:]
            member = message.mentions[0]
            role = discord.utils.get(message.guild.roles, name=r_name)
            if role:
                await member.add_roles(role)
                await message.channel.send(f"✅ تم إعطاء رتبة **{r_name}** لـ {member.mention}")

    await bot.process_commands(message)

# --- لوحة التحكم (Flask) ---
app = Flask(__name__)

@app.route('/')
def index():
    g = bot.guilds[0] if bot.guilds else None
    return render_template('index.html', 
                           member_count=g.member_count if g else 0,
                           ping=round(bot.latency * 1000),
                           open_tickets=len([c for c in bot.get_all_channels() if "ticket-" in c.name]))

@app.route('/update_settings', methods=['POST'])
def update_settings():
    f = request.form
    conn = sqlite3.connect('phantom_pro.db')
    conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?, ?, ?, ?)", 
                 (f['guild_id'], f['admin_roles'], f['channel_id'], f['log_channel'], f['category_id']))
    conn.commit()
    conn.close()
    asyncio.run_coroutine_threadsafe(setup_launcher(f['channel_id']), bot.loop)
    return "<h1>تم الحفظ وإرسال الزر!</h1><a href='/'>رجوع</a>"

async def setup_launcher(cid):
    ch = bot.get_channel(int(cid))
    if ch: await ch.send("نظام المساعدة | اضغط أدناه لفتح تذكرة جديدة", view=TicketLaunch())

@app.route('/add_auto_reply', methods=['POST'])
def add_reply():
    conn = sqlite3.connect('phantom_pro.db')
    conn.execute("INSERT INTO auto_replies VALUES (?, ?)", (request.form['keyword'], request.form['response']))
    conn.commit()
    conn.close()
    return "<h1>تم إضافة الرد!</h1><a href='/'>رجوع</a>"

@app.route('/create_mc_roles', methods=['POST'])
def create_mc():
    asyncio.run_coroutine_threadsafe(async_mc(request.form['guild_id']), bot.loop)
    return "<h1>جاري إنشاء الرتب...</h1><a href='/'>رجوع</a>"

async def async_mc(gid):
    guild = bot.get_guild(int(gid))
    if guild:
        for r in MC_ROLES:
            if not discord.utils.get(guild.roles, name=r):
                await guild.create_role(name=r, color=discord.Color.random())

@app.route('/broadcast', methods=['POST'])
def bdc():
    asyncio.run_coroutine_threadsafe(async_bdc(request.form['guild_id'], request.form['msg']), bot.loop)
    return "<h1>بدأ الإرسال في الخاص...</h1><a href='/'>رجوع</a>"

async def async_bdc(gid, msg):
    guild = bot.get_guild(int(gid))
    if guild:
        for m in guild.members:
            if not m.bot:
                try: await m.send(f"**إعلان جديد:**\n{msg}")
                except: continue

@bot.event
async def on_ready():
    bot.add_view(TicketLaunch())
    bot.add_view(TicketActions())
    print(f"--- البوت متصل باسم {bot.user} ---")

def run_web(): app.run(port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run("ضع_توكن_بوتك_هنا")
