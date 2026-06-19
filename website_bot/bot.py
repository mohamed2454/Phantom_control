import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, render_template, request, jsonify
import threading
import sqlite3
import asyncio

# --- 1. إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (guild_id TEXT PRIMARY KEY, admin_role_id TEXT, ticket_channel_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

def update_db(guild_id, admin_role, channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES (?, ?, ?)", (str(guild_id), str(admin_role), str(channel_id)))
    conn.commit()
    conn.close()

def get_db(guild_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT admin_role_id, ticket_channel_id FROM settings WHERE guild_id=?", (str(guild_id),))
    res = c.fetchone()
    conn.close()
    return res

# --- 2. كود بوت الديسكورد ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class TicketActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام (Claim)", style=discord.ButtonStyle.blurple, custom_id="claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = get_db(interaction.guild.id)
        admin_role_id = int(data[0]) if data else None
        
        if admin_role_id and discord.utils.get(interaction.user.roles, id=admin_role_id):
            await interaction.response.send_message(f"✅ تم استلام التذكرة بواسطة: {interaction.user.mention}")
            button.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message("❌ هذا الزر للإداريين فقط!", ephemeral=True)

    @discord.ui.button(label="إغلاق (Close)", style=discord.ButtonStyle.red, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 سيتم إغلاق التذكرة...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

class TicketLaunch(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        data = get_db(guild.id)
        admin_role_id = int(data[0]) if data else None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if admin_role_id:
            role = guild.get_role(admin_role_id)
            if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
        await interaction.response.send_message(f"✅ تم فتح تذكرتك: {channel.mention}", ephemeral=True)
        
        embed = discord.Embed(title="نظام التذاكر", description="انتظر رد الإدارة، يمكنك التحكم بالتذكرة من الأزرار.")
        await channel.send(embed=embed, view=TicketActions())

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketLaunch())
        self.add_view(TicketActions())

bot = MyBot()

# --- 3. كود لوحة التحكم (Website Dashboard) ---
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
    <head><title>لوحة تحكم البوت</title></head>
    <body style="font-family: sans-serif; text-align: center; background: #2c2f33; color: white;">
        <h1>Dashboard - Discord Bot</h1>
        <div style="background: #23272a; padding: 20px; display: inline-block; border-radius: 10px;">
            <form action="/update" method="POST">
                <h3>إعدادات التذاكر</h3>
                Server ID: <br><input type="text" name="guild_id"><br><br>
                Admin Role ID: <br><input type="text" name="admin_role"><br><br>
                Ticket Channel ID: <br><input type="text" name="channel_id"><br><br>
                <input type="submit" value="حفظ وإرسال رسالة التذكرة" style="background: #7289da; color: white; border: none; padding: 10px;">
            </form>
            <hr>
            <form action="/broadcast" method="POST">
                <h3>نظام البرودكاست</h3>
                Server ID: <br><input type="text" name="guild_id"><br><br>
                Message: <br><textarea name="msg"></textarea><br><br>
                <input type="submit" value="إرسال للجميع" style="background: #f04747; color: white; border: none; padding: 10px;">
            </form>
        </div>
    </body>
    </html>
    """

@app.route('/update', methods=['POST'])
def update():
    gid = request.form['guild_id']
    rid = request.form['admin_role']
    cid = request.form['channel_id']
    update_db(gid, rid, cid)
    
    # إرسال رسالة التذاكر في القناة المحددة
    asyncio.run_coroutine_threadsafe(send_ticket_msg(cid), bot.loop)
    return "<h1>تم الحفظ وإرسال الرسالة بنجاح!</h1><a href='/'>رجوع</a>"

async def send_ticket_msg(channel_id):
    channel = bot.get_channel(int(channel_id))
    if channel:
        embed = discord.Embed(title="فتح تذكرة جديدة", description="للتواصل مع الإدارة، اضغط على الزر أدناه.")
        await channel.send(embed=embed, view=TicketLaunch())

@app.route('/broadcast', methods=['POST'])
def broadcast():
    gid = request.form['guild_id']
    msg = request.form['msg']
    asyncio.run_coroutine_threadsafe(start_broadcast(gid, msg), bot.loop)
    return "<h1>بدأ إرسال البرودكاست...</h1><a href='/'>رجوع</a>"

async def start_broadcast(guild_id, msg):
    guild = bot.get_guild(int(guild_id))
    if guild:
        for member in guild.members:
            if not member.bot:
                try: await member.send(msg)
                except: continue

# --- 4. تشغيل الموقع والبوت معاً ---
def run_web():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    # تشغيل الموقع في خلفية الكود
    threading.Thread(target=run_web).start()
    # تشغيل البوت (ضع التوكن الخاص بك هنا)
    bot.run("MTQ5NzUzMzAxNTY3MTE3NzI0Ng.GLDmGQ.yTmOSKvEe_qBhfvwc39QuxBvgvkwBhZp9dZz0A")