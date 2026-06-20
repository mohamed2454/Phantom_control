import discord
from discord.ext import commands
from flask import Flask, render_template, request, jsonify
import threading, asyncio, sqlite3, os, math, time, socket, aiohttp
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
            log_action_db("TICKET_CLOSE", str(i.user.id), f"تم إغلاق تذكرة: {i.channel.name}")
            await i.channel.delete()
        except Exception as e:
            log_error("TICKET_CLOSE", str(e))
            await i.followup.send("❌ حدث خطأ في إغلاق التذكرة", ephemeral=True)

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
    
    try:
        # التحقق من الحظر
        if is_user_banned(str(message.author.id), str(message.guild.id)):
            return

        # --- ميزة إرسال صورة الخط الفاصل تلقائياً وحذف رسالة العضو ---
        if message.content.strip() == "خط":
            # محاولة حذف رسالة العضو ليكون الشات منظماً
            try:
                await message.delete()
            except discord.Forbidden:
                log_warning("LINE_COMMAND", f"البوت يفتقد صلاحية 'إدارة الرسائل' لحذف الكلمة في القناة {message.channel.id}")
            except Exception as e:
                log_error("LINE_COMMAND_DELETE", str(e))

            # إرسال الصورة الفاصلة
            if os.path.exists("line.png"):
                await message.channel.send(file=discord.File("line.png"))
            else:
                await message.channel.send("⚠️ يرجى رفع صورة الخط الفاصل في مجلد البوت باسم `line.png` أولاً لكي أتمكن من إرسالها!")
            return

        # --- نظام إضافة وإزالة رتب الماين كرافت عبر شات الديسكورد (+ / -) ---
        content = message.content.strip()
        if content.startswith('+') or content.startswith('-'):
            is_add = content.startswith('+')
            raw_text = content[1:].strip()
            
            if message.mentions:
                target_member = message.mentions[0]
                # تنظيف النص لاستخراج اسم الرتبة فقط بدون المنشن
                role_query = raw_text.replace(target_member.mention, "").replace(f"<@!{target_member.id}>", "").strip()
                
                # البحث عن الرتبة المطابقة في قائمة MC_ROLES
                matched_role_name = None
                for r_name in MC_ROLES:
                    if r_name.lower() == role_query.lower() or r_name.lower() in role_query.lower():
                        matched_role_name = r_name
                        break
                
                if matched_role_name:
                    # التحقق من صلاحية العضو المرسل للأمر
                    if not message.author.guild_permissions.manage_roles:
                        await message.channel.send("❌ لا تمتلك صلاحية `إدارة الرتب (Manage Roles)` لاستخدام هذا الأمر.")
                        return
                    
                    # البحث عن الرتبة داخل السيرفر
                    guild_role = discord.utils.get(message.guild.roles, name=matched_role_name)
                    if not guild_role:
                        await message.channel.send(f"❌ لم يتم العثور على رتبة `{matched_role_name}` في السيرفر. قم بإنشائها أولاً من لوحة التحكم.")
                        return
                    
                    try:
                        if is_add:
                            await target_member.add_roles(guild_role)
                            await message.channel.send(f"✅ تم منح رتبة `{matched_role_name}` للعضو {target_member.mention}")
                        else:
                            await target_member.remove_roles(guild_role)
                            await message.channel.send(f"✅ تم إزالة رتبة `{matched_role_name}` من العضو {target_member.mention}")
                    except discord.Forbidden:
                        await message.channel.send("❌ البوت لا يملك صلاحية كافية لتعديل هذه الرتبة. تأكد من سحب رتبة البوت لتكون **أعلى** من رتب Minecraft في قائمة رتب السيرفر (Server Settings -> Roles).")
                    except Exception as e:
                        log_error("ROLE_CHANGE", str(e))
                    return  # إيقاف المعالجة لعدم تداخلها مع الردود التلقائية

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # الردود التلقائية
        cursor.execute("SELECT response FROM auto_replies WHERE keyword=?", (message.content,))
        r = cursor.fetchone()
        if r: 
            await message.channel.send(r[0])
        
        # نظام الـ XP
        cursor.execute("INSERT OR IGNORE INTO levels (user_id, xp, level) VALUES (?, 0, 1)", (str(message.author.id),))
        cursor.execute("UPDATE levels SET xp = xp + 1 WHERE user_id = ?", (str(message.author.id),))
        conn.commit()
        
        # حفظ السجل
        log_action_db("MESSAGE", str(message.author.id), f"رسالة في {message.guild.name}")
        
        conn.close()
    except Exception as e:
        log_error("ON_MESSAGE", str(e))
    
    await bot.process_commands(message)

# --- أوامر البوت ---
@bot.command(name="xp")
async def check_xp(ctx):
    """فحص XP المستخدم"""
    try:
        xp, level = get_user_xp(ctx.author.id)
        embed = create_xp_embed(ctx.author, xp, level)
        await ctx.send(embed=embed)
    except Exception as e:
        log_error("XP_COMMAND", str(e))
        await ctx.send("❌ حدث خطأ في عرض الإحصائيات")

@bot.command(name="warn")
@commands.has_permissions(administrator=True)
async def warn_user(ctx, user: discord.User, *, reason="بدون سبب"):
    """إعطاء تحذير للمستخدم"""
    try:
        count = add_warning(str(user.id), str(ctx.guild.id), reason, str(ctx.author.id))
        embed = discord.Embed(
            title="⚠️ تحذير جديد",
            description=f"تم تحذير {user.mention}\n**السبب:** {reason}\n**عدد التحذيرات:** {count}",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        log_action_db("WARNING", str(user.id), f"تحذير من {ctx.author.name}: {reason}")
    except Exception as e:
        log_error("WARN_COMMAND", str(e))
        await ctx.send("❌ حدث خطأ")

@bot.command(name="ban")
@commands.has_permissions(administrator=True)
async def ban_user(ctx, user: discord.User, *, reason="بدون سبب"):
    """حظر المستخدم"""
    try:
        if add_ban(str(user.id), str(ctx.guild.id), reason, str(ctx.author.id)):
            embed = discord.Embed(
                title="🔨 حظر",
                description=f"تم حظر {user.mention}\n**السبب:** {reason}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            await ctx.guild.ban(user, reason=reason)
            log_action_db("BAN", str(user.id), f"حظر من {ctx.author.name}: {reason}")
    except Exception as e:
        log_error("BAN_COMMAND", str(e))
        await ctx.send("❌ حدث خطأ في الحظر")

# --- لوحة التحكم (Flask) ---
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

@app.route('/')
def home():
    try:
        status = "متصل ✅" if bot.is_ready() else "جاري الاتصال... ⏳"
        g = bot.guilds[0] if bot.guilds else None
        ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
        tickets = len([c for c in bot.get_all_channels() if "ticket-" in c.name])
        
        # جلب قائمة السيرفرات المتصل بها البوت تلقائياً
        guilds_list = []
        if bot.is_ready():
            for guild in bot.guilds:
                guilds_list.append({
                    'id': str(guild.id),
                    'name': guild.name
                })
        
        return render_template('index.html', 
                             status=status, 
                             member_count=g.member_count if g else 0, 
                             ping=ping, 
                             open_tickets=tickets,
                             bot_name=bot.user.name if bot.user else "البوت",
                             guilds=guilds_list) # تمرير السيرفرات للواجهة
    except Exception as e:
        log_error("HOME_ROUTE", str(e))
        return "خطأ في التحميل", 500

# نقطة برمجية جديدة (API) لجلب تفاصيل السيرفر بمجرد اختياره في الواجهة
@app.route('/api/guild_details/<guild_id>')
def guild_details(guild_id):
    try:
        if not bot.is_ready():
            return jsonify({'error': 'البوت غير جاهز بعد'}), 503
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return jsonify({'error': 'لم يتم العثور على السيرفر المطلوب'}), 404
        
        # جلب القنوات الكتابية
        channels = [{'id': str(c.id), 'name': c.name} for c in guild.text_channels]
        # جلب فئات السيرفر (Categories) لكي يحدد منها فئة التذاكر
        categories = [{'id': str(cat.id), 'name': cat.name} for cat in guild.categories]
        # جلب الرتب باستثناء رتبة الجميع @everyone ورتب البوتات التلقائية
        roles = [{'id': str(r.id), 'name': r.name} for r in guild.roles if not r.is_default() and not r.managed]
        
        return jsonify({
            'channels': channels,
            'categories': categories,
            'roles': roles
        })
    except Exception as e:
        log_error("GUILD_DETAILS_API", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """الحصول على إحصائيات البوت"""
    try:
        status = "متصل ✅" if bot.is_ready() else "معطل ❌"
        g = bot.guilds[0] if bot.guilds else None
        ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM auto_replies")
        replies = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM levels")
        users = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': status,
            'guilds': len(bot.guilds),
            'members': g.member_count if g else 0,
            'ping': ping,
            'auto_replies': replies,
            'total_users': users
        })
    except Exception as e:
        log_error("STATS_API", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/update_settings', methods=['POST'])
@require_admin
def update():
    try:
        f = request.form
        valid, msg = validate_input(f, ['guild_id', 'channel_id'])
        if not valid:
            return f"<h1>❌ خطأ: {msg}</h1><a href='/'>رجوع</a>"
        
        # دمج الرتب المتعددة وحفظها كنص مفصول بفاصلة
        roles_list = request.form.getlist('admin_roles')
        admin_roles_str = ",".join(roles_list)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # استعلام الحفظ والتعديل الآمن مع تصحيح الأعمدة الـ 6 لجدول config
        cursor.execute("""
            INSERT OR REPLACE INTO config (guild_id, admin_roles, channel_id, log_channel, category_id, created_at) 
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (f['guild_id'], admin_roles_str, f['channel_id'], 
             f.get('log_channel', ''), f.get('category_id', '')))
        
        conn.commit()
        conn.close()
        
        # استدعاء الدالة المساعدة بشكل آمن على خيط البوت لتفادي خطأ Event Loop
        asyncio.run_coroutine_threadsafe(
            send_ticket_launcher(int(f['channel_id'])), 
            bot.loop
        )
        
        log_action_db("SETTINGS_UPDATE", "unknown", f"تحديث إعدادات السيرفر {f['guild_id']}")
        return "<h1>✅ تم الحفظ!</h1><a href='/'>رجوع</a>"
    except Exception as e:
        log_error("UPDATE_SETTINGS", str(e))
        return f"<h1>❌ خطأ: {e}</h1><a href='/'>رجوع</a>"

@app.route('/add_auto_reply', methods=['POST'])
@require_admin
def add_reply():
    try:
        keyword = sanitize_input(request.form.get('keyword', ''))
        response = sanitize_input(request.form.get('response', ''))
        
        if not keyword or not response:
            return "<h1>❌ الكلمة المفتاحية والرد مطلوبان!</h1><a href='/'>رجوع</a>"
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO auto_replies (keyword, response, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)", 
                      (keyword, response))
        conn.commit()
        conn.close()
        
        log_action_db("AUTO_REPLY_ADD", "unknown", f"رد تلقائي: {keyword}")
        return "<h1>✅ تمت إضافة الرد!</h1><a href='/'>رجوع</a>"
    except Exception as e:
        log_error("ADD_REPLY", str(e))
        return f"<h1>❌ خطأ: {e}</h1><a href='/'>رجوع</a>"

@app.route('/list_replies')
def list_replies():
    """عرض جميع الردود التلقائية"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, keyword, response FROM auto_replies")
        replies = cursor.fetchall()
        conn.close()
        
        return render_template('replies.html', replies=replies)
    except Exception as e:
        log_error("LIST_REPLIES", str(e))
        return "خطأ في التحميل", 500

@app.route('/broadcast', methods=['POST'])
@require_admin
def broadcast():
    try:
