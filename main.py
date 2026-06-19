import discord
from discord.ext import commands
from flask import Flask, render_template, request
import threading
import asyncio
import sqlite3

# --- إعدادات البوت ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- قاعدة البيانات ---
def update_settings(guild_id, admin_role, channel_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS config (guild_id TEXT PRIMARY KEY, admin_role TEXT, channel_id TEXT)")
    c.execute("INSERT OR REPLACE INTO config VALUES (?, ?, ?)", (guild_id, admin_role, channel_id))
    conn.commit()
    conn.close()

def get_settings(guild_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT admin_role, channel_id FROM config WHERE guild_id=?", (str(guild_id),))
    res = c.fetchone()
    conn.close()
    return res

# --- نظام التذاكر (الأزرار المحدثة) ---
class TicketActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام التذكرة ✋", style=discord.ButtonStyle.primary, custom_id="claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. أخبر ديسكورد أنك استلمت التفاعل فوراً
        await interaction.response.defer() 
        
        # 2. تنفيذ المنطق
        await interaction.followup.send(f"التذكرة قيد المتابعة من قبل: {interaction.user.mention}")
        button.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="إغلاق 🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("🔒 سيتم حذف القناة بعد 5 ثوانٍ...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketLaunch(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="open")
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        # تأجيل الرد لأن إنشاء القناة قد يستغرق وقتاً
        await interaction.response.defer(ephemeral=True)
        
        settings = get_settings(interaction.guild.id)
        admin_role_id = int(settings[0]) if settings else None
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if admin_role_id:
            role = interaction.guild.get_role(admin_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            channel = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
            # استخدام followup بدلاً من response لأننا قمنا بعمل defer
            await interaction.followup.send(f"✅ تم فتح تذكرتك: {channel.mention}", ephemeral=True)
            await channel.send(f"مرحباً {interaction.user.mention}، سيتم الرد عليك قريباً.", view=TicketActions())
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء إنشاء القناة: {e}", ephemeral=True)

# --- الموقع (Flask) ---
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

async def async_setup_tickets(cid):
    channel = bot.get_channel(int(cid))
    if channel:
        view = TicketLaunch()
        await channel.send("مركز المساعدة: اضغط على الزر أدناه لفتح تذكرة.", view=view)

@app.route('/setup_tickets', methods=['POST'])
def setup_tickets():
    gid = request.form['guild_id']
    rid = request.form['admin_role']
    cid = request.form['channel_id']
    update_settings(gid, rid, cid)
    asyncio.run_coroutine_threadsafe(async_setup_tickets(cid), bot.loop)
    return "<h1>تم الإرسال بنجاح!</h1><a href='/'>رجوع</a>"

async def async_broadcast(gid, msg):
    guild = bot.get_guild(int(gid))
    if guild:
        for member in guild.members:
            if not member.bot:
                try: await member.send(msg)
                except: continue

@app.route('/broadcast', methods=['POST'])
def broadcast():
    gid = request.form['guild_id']
    msg = request.form['msg']
    asyncio.run_coroutine_threadsafe(async_broadcast(gid, msg), bot.loop)
    return "<h1>بدأ الإرسال...</h1><a href='/'>رجوع</a>"

def run_site():
    app.run(port=5000, debug=False, use_reloader=False)

@bot.event
async def on_ready():
    bot.add_view(TicketLaunch())
    bot.add_view(TicketActions())
    print(f"تم التشغيل: {bot.user}")

if __name__ == "__main__":
    t = threading.Thread(target=run_site)
    t.daemon = True
    t.start()
    # ضع التوكن الخاص بك هنا
    bot.run("MTQ5NzUzMzAxNTY3MTE3NzI0Ng.GLDmGQ.yTmOSKvEe_qBhfvwc39QuxBvgvkwBhZp9dZz0A")