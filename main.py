import discord
from discord.ext import commands
from flask import Flask, render_template, request, jsonify
import threading, asyncio, sqlite3, os, math, time, socket, aiohttp, io
from dotenv import load_dotenv
from utils import sanitize_input, is_valid_channel_id, is_valid_guild_id, create_xp_embed, get_user_xp
from database import init_db, backup_db, log_action_db, add_warning, get_warnings, add_ban, is_user_banned
from permissions import require_admin, check_guild_permissions, validate_input
from logger_config import log_action, log_error, log_warning

# تحميل متغيرات البيئة
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')

# تم تعديل المنفذ ليقرأ تلقائياً من المتغير PORT الخاص بـ Railway
FLASK_PORT = int(os.getenv('PORT', 8080))

MC_ROLES = ["Steve", "Alex", "Villager", "Zombie", "Creeper", "Enderman", "Skeleton", "Spider", "Piglin", "Ghast", 
            "Blaze", "Iron Golem", "Wither", "Ender Dragon", "Warden", "Herobrine", "Axolotl", "Bee", "Fox", "Wolf"]

# تم تعديل مسار قاعدة البيانات ليدعم مساحة التخزين الدائمة
DB_PATH = os.getenv('DB_PATH', 'phantom_pro.db')

# --- البوت المطور ---
class PhantomBot(commands.Bot):
    async def setup_hook(self):
        try:
            self.http.connector = aiohttp.TCPConnector(family=socket.AF_INET)
            self.add_view(TicketLaunch())
            self.add_view(TicketActions())
            log_action("BOT_SETUP", "تم إعداد البوت بنجاح")
        except Exception as e:
            log_error("BOT_SETUP", str(e))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
bot = PhantomBot(command_prefix="!", intents=intents)

# --- أنظمة التذاكر ---
class TicketActions(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
    
    @discord.ui.button(label="استلام ✋", style=discord.ButtonStyle.primary, custom_id="c_final")
    async def claim(self, i, b):
        try:
            await i.response.send_message(f"✅ استلم {i.user.mention} التذكرة.")
            log_action_db("TICKET_CLAIM", str(i.user.id), f"تم استلام تذكرة في {i.channel.name}")
        except Exception as e:
            log_error("TICKET_CLAIM", str(e))
    
    @discord.ui.button(label="إغلاق 🔒", style=discord.ButtonStyle.danger, custom_id="l_final")
    async def close_ticket(self, i, b):
        try:
            await i.response.defer()
            
            # 1. جمع رسائل القناة لإنشاء سجل المحادثة (Transcript)
            messages = []
            messages.append(f"=== سجل محادثة التذكرة المغلقة: {i.channel.name} ===")
            messages.append(f"أغلقت بواسطة: {str(i.user)}")
            messages.append("=" * 50 + "\n")
            
            async for msg in i.channel.history(limit=None, oldest_first=True):
                time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
                messages.append(f"[{time_str}] {str(msg.author)}: {msg.content}")
                if msg.attachments:
                    for att in msg.attachments:
                        messages.append(f"   └─ [ملف مرفق]: {att.url}")
            
            transcript_text = "\n".join(messages)
            
            # إنشاء الملف البرمجي مباشرة في الذاكرة
            file_data = io.BytesIO(transcript_text.encode('utf-8'))
            
            # 2. إرسال سجل المحادثة للشخص الذي أغلق التذكرة في الخاص (DM)
            try:
                file_data.seek(0)
                file_to_user = discord.File(file_data, filename=f"transcript-{i.channel.name}.txt")
                await i.user.send(f"📄 سجل محادثة التذكرة المغلقة `{i.channel.name}` الخاص بك:", file=file_to_user)
            except discord.Forbidden:
                # العضو يغلق الخاص لديه
                pass
            
            # 3. إرسال السجل في قناة السجلات (Log Channel) إذا كانت مهيأة في قاعدة البيانات
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT log_channel FROM config WHERE guild_id=?", (str(i.guild.id),))
                row = cursor.fetchone()
                conn.close()
                
                if row and row[0]:
                    log_channel_id = int(row[0])
                    log_channel = bot.get_channel(log_channel_id)
                    if not log_channel:
                        try:
                            log_channel = await bot.fetch_channel(log_channel_id)
                        except:
                            pass
                    
                    if log_channel:
                        file_data.seek(0)
                        file_to_log = discord.File(file_data, filename=f"transcript-{i.channel.name}.txt")
                        embed = discord.Embed(
                            title="🔒 إغلاق تذكرة",
                            description=f"**التذكرة:** `{i.channel.name}`\n**أغلقت بواسطة:** {i.user.mention}",
                            color=discord.Color.red()
                        )
                        await log_channel.send(embed=embed, file=file_to_log)
            except Exception as log_err:
                log_error("TICKET_LOG_TRANSCRIPT", str(log_err))

            # 4. تسجيل العملية في قاعدة البيانات ثم حذف القناة
            log_action_db("TICKET_CLOSE", str(i.user.id), f"تم إغلاق تذكرة: {i.channel.name}")
            await i.channel.delete()
            
        except Exception as e:
            log_error("TICKET_CLOSE", str(e))
            try:
                await i.followup.send("❌ حدث خطأ في إغلاق التذكرة والمحادثة", ephemeral=True)
            except:
                pass

class TicketLaunch(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
    
    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="o_final")
    async def open(self, i, b):
        try:
            await i.response.defer(ephemeral=True)
            ch = await i.guild.create_text_channel(f"ticket-{i.user.name}")
            await i.followup.send(f"✅ تم فتح تذكرتك: {ch.mention}", ephemeral=True)
            await ch.send(f"أهلاً {i.user.mention}\nاختر الإجراء المطلوب:", view=TicketActions())
            log_action_db("TICKET_OPEN", str(i.user.id), f"فتح تذكرة جديدة: {ch.name}")
        except Exception as e:
            log_error("TICKET_OPEN", str(e))
            await i.response.send_message("❌ حدث خطأ في فتح التذكرة!", ephemeral=True)

# دالة مساعدة لتجهيز وإرسال رسالة التذاكر بالكامل داخل خيط البوت (Thread) لتفادي أخطاء الـ Event Loop
async def send_ticket_launcher(channel_id):
    try:
        # استخدام fetch_channel لضمان جلب القناة مباشرة من ديسكورد وتجنب الـ Cache الفارغ
        channel = await bot.fetch_channel(channel_id)
        if channel:
            await channel.send("🎫 فتح تذكرة", view=TicketLaunch())
            log_action("TICKET_LAUNCH", f"تم إرسال رسالة التذاكر بنجاح في القناة {channel_id}")
        else:
            log_error("TICKET_LAUNCH", f"لم يتم العثور على القناة {channel_id}")
    except discord.Forbidden:
        log_error("TICKET_LAUNCH", f"فشل الإرسال: البوت يفتقد لصلاحية إرسال الرسائل أو رؤية القناة {channel_id}")
    except Exception as e:
        log_error("TICKET_LAUNCH", f"حدث خطأ أثناء إرسال رسالة التذاكر: {e}")

# --- فعاليات البوت ---
@bot.event
async def on_ready():
    log_action("BOT_READY", f"البوت {bot.user} متصل وجاهز للعمل")
    print(f"--- ✅ {bot.user} متصل ---")
    
    # نسخ احتياطي يومي
    backup_db()

@bot.event
async def on_message(message):
    if message.author.bot: 
        return
    
    tr
