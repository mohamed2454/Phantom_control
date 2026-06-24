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

# دالة مساعدة للتحقق مما إذا كان العضو إدارياً
def is_ticket_admin(member, guild_id):
    if member == member.guild.owner or member.guild_permissions.administrator:
        return True
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT admin_roles FROM config WHERE guild_id=?", (str(guild_id),))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            admin_roles_list = row[0].split(",")
            for role in member.roles:
                if str(role.id) in admin_roles_list:
                    return True
    except Exception as e:
        log_error("CHECK_TICKET_ADMIN", str(e))
    
    return False

# --- أنظمة التذاكر ---
class TicketActions(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
    
    @discord.ui.button(label="استلام ✋", style=discord.ButtonStyle.primary, custom_id="c_final")
    async def claim(self, i, b):
        try:
            if not is_ticket_admin(i.user, i.guild.id):
                await i.response.send_message("❌ هذا الإجراء مخصص للإداريين فقط!", ephemeral=True)
                return

            await i.response.send_message(f"✅ استلم {i.user.mention} التذكرة.")
            log_action_db("TICKET_CLAIM", str(i.user.id), f"تم استلام تذكرة في {i.channel.name}")
        except Exception as e:
            log_error("TICKET_CLAIM", str(e))
    
    @discord.ui.button(label="إغلاق 🔒", style=discord.ButtonStyle.danger, custom_id="l_final")
    async def close_ticket(self, i, b):
        try:
            if not is_ticket_admin(i.user, i.guild.id):
                await i.response.send_message("❌ هذا الإجراء مخصص للإداريين فقط!", ephemeral=True)
                return

            await i.response.defer()
            
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
            file_data = io.BytesIO(transcript_text.encode('utf-8'))
            
            try:
                file_data.seek(0)
                file_to_user = discord.File(file_data, filename=f"transcript-{i.channel.name}.txt")
                await i.user.send(f"📄 سجل محادثة التذكرة المغلقة `{i.channel.name}` الخاص بك:", file=file_to_user)
            except discord.Forbidden:
                pass
            
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

            log_action_db("TICKET_CLOSE", str(i.user.id), f"تم إغلاق تذكرة: {i.channel.name}")
            await i.channel.delete()
            
        except Exception as e:
            log_error("TICKET_CLOSE", str(e))
            try:
                await i.followup.send("❌ حدث خطأ في إغلاق التذكرة والمحادثة", ephemeral=True)
            except:
                pass

# --- نظام قائمة اختيار أسباب فتح التذاكر ---
class TicketReasonSelect(discord.ui.Select):
    def __init__(self, reasons):
        options = []
        for r_id, r_text in reasons:
            options.append(discord.SelectOption(label=r_text, value=str(r_id)))
        super().__init__(placeholder="👉 الرجاء تحديد سبب فتح التذكرة للبدء...", min_values=1, max_values=1, options=options)
    
    async def callback(self, i: discord.Interaction):
        try:
            await i.response.defer()
            selected_id = self.values[0]
            
            selected_text = "غير محدد"
            for opt in self.options:
                if opt.value == selected_id:
                    selected_text = opt.label
                    break
            
            embed = discord.Embed(
                title="🎫 تفاصيل التذكرة الحالية",
                description=f"**صاحب التذكرة:** {i.user.mention}\n**السبب المختار:** `{selected_text}`",
                color=discord.Color.blue()
            )
            await i.edit_original_response(content="✅ تم تحديد سبب فتح التذكرة بنجاح.", embed=embed, view=TicketActions())
        except Exception as e:
            log_error("TICKET_REASON_SELECT_CALLBACK", str(e))

class TicketReasonView(discord.ui.View):
    def __init__(self, reasons):
        super().__init__(timeout=None)
        self.add_item(TicketReasonSelect(reasons))

class TicketLaunch(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
    
    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="o_final")
    async def open(self, i, b):
        try:
            await i.response.defer(ephemeral=True)
            
            reasons = []
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT id, reason FROM ticket_reasons WHERE guild_id=?", (str(i.guild.id),))
                reasons = cursor.fetchall()
                conn.close()
            except Exception as e:
                log_error("GET_REASONS", str(e))

            ch = await i.guild.create_text_channel(f"ticket-{i.user.name}")
            await i.followup.send(f"✅ تم فتح تذكرتك: {ch.mention}", ephemeral=True)
            
            if reasons:
                await ch.send(f"أهلاً {i.user.mention}\nالرجاء تحديد سبب فتح التذكرة من القائمة أدناه للبدء:", view=TicketReasonView(reasons))
            else:
                await ch.send(f"أهلاً {i.user.mention}\nاختر الإجراء المطلوب:", view=TicketActions())
                
            log_action_db("TICKET_OPEN", str(i.user.id), f"فتح تذكرة جديدة: {ch.name}")
        except Exception as e:
            log_error("TICKET_OPEN", str(e))
            await i.response.send_message("❌ حدث خطأ في فتح التذكرة!", ephemeral=True)

async def send_ticket_launcher(channel_id):
    try:
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
    backup_db()

@bot.event
async def on_message(message):
    if message.author.bot: 
        return
    
    try:
        if is_user_banned(str(message.author.id), str(message.guild.id)):
            return

        if message.content.strip() == "خط":
            try:
                await message.delete()
            except discord.Forbidden:
                log_warning("LINE_COMMAND", f"البوت يفتقد صلاحية 'إدارة الرسائل' لحذف الكلمة في القناة {message.channel.id}")
            except Exception as e:
                log_error("LINE_COMMAND_DELETE", str(e))

            if os.path.exists("line.png"):
                await message.channel.send(file=discord.File("line.png"))
            else:
                await message.channel.send("⚠️ يرجى رفع صورة الخط الفاصل في مجلد البوت باسم `line.png` أولاً لكي أتمكن من إرسالها!")
            return

        content = message.content.strip()
        if content.startswith('+') or content.startswith('-'):
            is_add = content.startswith('+')
            raw_text = content[1:].strip()
            
            if message.mentions:
                target_member = message.mentions[0]
                role_query = raw_text.replace(target_member.mention, "").replace(f"<@!{target_member.id}>", "").strip()
                
                matched_role_name = None
                for r_name in MC_ROLES:
                    if r_name.lower() == role_query.lower() or r_name.lower() in role_query.lower():
                        matched_role_name = r_name
                        break
                
                if matched_role_name:
                    if not message.author.guild_permissions.manage_roles:
                        await message.channel.send("❌ لا تمتلك صلاحية `إدارة الرتب (Manage Roles)` لاستخدام هذا الأمر.")
                        return
                    
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
                    return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT response FROM auto_replies WHERE keyword=?", (message.content,))
        r = cursor.fetchone()
        if r: 
            await message.channel.send(r[0])
        
        cursor.execute("INSERT OR IGNORE INTO levels (user_id, xp, level) VALUES (?, 0, 1)", (str(message.author.id),))
        cursor.execute("UPDATE levels SET xp = xp + 1 WHERE user_id = ?", (str(message.author.id),))
        conn.commit()
        
        log_action_db("MESSAGE", str(message.author.id), f"رسالة في {message.guild.name}")
        conn.close()
    except Exception as e:
        log_error("ON_MESSAGE", str(e))
    
    await bot.process_commands(message)

# --- أوامر البوت ---
@bot.command(name="xp")
async def check_xp(ctx):
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
                             guilds=guilds_list)
    except Exception as e:
        log_error("HOME_ROUTE", str(e))
        return "خطأ في التحميل", 500

# نقطة برمجية مطورة لجلب تفاصيل السيرفر متضمنة الإعدادات الحالية
@app.route('/api/guild_details/<guild_id>')
def guild_details(guild_id):
    try:
        if not bot.is_ready():
            return jsonify({'error': 'البوت غير جاهز بعد'}), 503
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return jsonify({'error': 'لم يتم العثور على السيرفر المطلوب'}), 404
        
        channels = [{'id': str(c.id), 'name': c.name} for c in guild.text_channels]
        categories = [{'id': str(cat.id), 'name': cat.name} for cat in guild.categories]
        roles = [{'id': str(r.id), 'name': r.name} for r in guild.roles if not r.is_default() and not r.managed]
        
        # جلب خيارات التذاكر المضافة
        reasons = []
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, reason FROM ticket_reasons WHERE guild_id=?", (str(guild_id),))
        rows = cursor.fetchall()
        
        # جلب البيانات الحالية من الـ config لكي نعرضها افتراضياً
        cursor.execute("SELECT admin_roles, channel_id, log_channel, category_id FROM config WHERE guild_id=?", (str(guild_id),))
        cfg_row = cursor.fetchone()
        conn.close()
        
        config_data = {}
        if cfg_row:
            config_data = {
                'admin_roles': cfg_row[0].split(',') if cfg_row[0] else [],
                'channel_id': cfg_row[1],
                'log_channel': cfg_row[2],
                'category_id': cfg_row[3]
            }
        else:
            config_data = {
                'admin_roles': [],
                'channel_id': '',
                'log_channel': '',
                'category_id': ''
            }
        
        reasons = [{'id': r[0], 'reason': r[1]} for r in rows]
        
        return jsonify({
            'channels': channels,
            'categories': categories,
            'roles': roles,
            'reasons': reasons,
            'config': config_data
        })
    except Exception as e:
        log_error("GUILD_DETAILS_API", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
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

# تعديل راوت التحديث لدعم طلبات AJAX و AJAX JSON بشكل مستقر
@app.route('/update_settings', methods=['POST'])
@require_admin
def update():
    try:
        f = request.form
        valid, msg = validate_input(f, ['guild_id', 'channel_id'])
        if not valid:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'error': msg}), 400
            return f"<h1>❌ خطأ: {msg}</h1><a href='/'>رجوع</a>"
        
        # جلب الرتب المحددة من مربعات الاختيار في الـ Form
        roles_list = request.form.getlist('admin_roles')
        admin_roles_str = ",".join(roles_list)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO config (guild_id, admin_roles, channel_id, log_channel, category_id, created_at) 
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (f['guild_id'], admin_roles_str, f['channel_id'], 
             f.get('log_channel', ''), f.get('category_id', '')))
        
        conn.commit()
        conn.close()
        
        asyncio.run_coroutine_threadsafe(
            send_ticket_launcher(int(f['channel_id'])), 
            bot.loop
        )
        
        log_action_db("SETTINGS_UPDATE", "unknown", f"تحديث إعدادات السيرفر {f['guild_id']}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({'success': True, 'message': 'تم حفظ الإعدادات بنجاح!'})
            
        return "<h1>✅ تم الحفظ!</h1><a href='/'>رجوع</a>"
    except Exception as e:
        log_error("UPDATE_SETTINGS", str(e))
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({'error': str(e)}), 500
        return f"<h1>❌ خطأ: {e}</h1><a href='/'>رجوع</a>"

# راوت الحفظ المجمع والنهائي لخيارات التذاكر دفعة واحدة
@app.route('/api/save_ticket_reasons', methods=['POST'])
@require_admin
def save_ticket_reasons():
    try:
        data = request.json
        gid = data.get('guild_id')
        reasons = data.get('reasons', [])
        
        if not gid:
            return jsonify({'error': 'معرف السيرفر مطلوب'}), 400
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # مسح جميع الأسباب القديمة لإعادة حفظ القائمة النهائية والجديدة
        cursor.execute("DELETE FROM ticket_reasons WHERE guild_id=?", (str(gid),))
        
        for r_text in reasons:
            r_text = sanitize_input(r_text)
            if r_text:
                cursor.execute("INSERT INTO ticket_reasons (guild_id, reason) VALUES (?, ?)", (str(gid), r_text))
                
        conn.commit()
        conn.close()
        
        log_action_db("TICKET_REASONS_SAVE", "unknown", f"تحديث أسباب التذاكر للسيرفر {gid}")
        return jsonify({'success': True})
    except Exception as e:
        log_error("SAVE_REASONS_API", str(e))
        return jsonify({'error': str(e)}), 500

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
        gid = request.form.get('guild_id')
        msg = sanitize_input(request.form.get('msg', ''))
        
        if not gid or not msg:
            return "<h1>❌ السيرفر والرسالة مطلوبان!</h1><a href='/'>رجوع</a>"
        
        async def run_bdc():
            try:
                guild = bot.get_guild(int(gid))
                if not guild:
                    log_warning("BROADCAST", f"السيرفر {gid} لم يُعثر عليه")
                    return
                
                count = 0
                for m in guild.members:
                    if not m.bot:
                        try:
                            user_mention = f"<@{m.id}>"
                            personalized_msg = (
                                msg.replace("{mention}", user_mention)
                                   .replace("{منشن}", user_mention)
                                   .replace("{name}", m.name)
                                   .replace("{اسم}", m.name)
                            )
                            await m.send(personalized_msg)
                            count += 1
                        except:
                            pass
                
                log_action_db("BROADCAST", "unknown", f"بث إلى {count} عضو")
            except Exception as e:
                log_error("BROADCAST", str(e))
        
        asyncio.run_coroutine_threadsafe(run_bdc(), bot.loop)
        return "<h1>✅ جاري إرسال البرودكاست...</h1><a href='/'>رجوع</a>"
    except Exception as e:
        log_error("BROADCAST", str(e))
        return f"<h1>❌ خطأ: {e}</h1><a href='/'>رجوع</a>"

@app.route('/create_mc_roles', methods=['POST'])
@require_admin
def mc_roles():
    try:
        gid = request.form.get('guild_id')
        if not gid:
            return "<h1>❌ السيرفر مطلوب!</h1><a href='/'>رجوع</a>"
        
        async def make():
            try:
                g = bot.get_guild(int(gid))
                if not g:
                    log_warning("MC_ROLES", f"السيرفر {gid} لم يُعثر عليه")
                    return
                
                created = 0
                for r in MC_ROLES:
                    try:
                        await g.create_role(name=r, color=discord.Color.random())
                        created += 1
                    except:
                        pass
                
                log_action_db("MC_ROLES", "unknown", f"تم إنشاء {created} رتب Minecraft")
            except Exception as e:
                log_error("MC_ROLES", str(e))
        
        asyncio.run_coroutine_threadsafe(make(), bot.loop)
        return "<h1>✅ جاري إنشاء الرتب...</h1><a href='/'>رجوع</a>"
    except Exception as e:
        log_error("MC_ROLES", str(e))
        return f"<h1>❌ خطأ: {e}</h1><a href='/'>رجوع</a>"

@app.errorhandler(404)
def not_found(e):
    return "<h1>❌ الصفحة غير موجودة</h1><a href='/'>الرئيسية</a>", 404

@app.errorhandler(500)
def server_error(e):
    log_error("SERVER_ERROR", str(e))
    return "<h1>❌ خطأ في السيرفر</h1><a href='/'>الرئيسية</a>", 500

def run_web():
    log_action("FLASK", f"بدء خادم الويب على {FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    log_action("APP_START", "بدء تطبيق Phantom Bot")
    init_db()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS ticket_reasons 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, reason TEXT)''')
        conn.commit()
        conn.close()
        log_action("DATABASE", "تم التحقق من تهيئة جدول ticket_reasons بنجاح")
    except Exception as e:
        log_error("DB_TICKET_REASONS_INIT", str(e))
        
    threading.Thread(target=run_web, daemon=True).start()
    log_action("WEB_SERVER", "خادم الويب بدأ")
    
    while True:
        try:
            if TOKEN:
                bot.run(TOKEN)
            else:
                log_error("TOKEN", "لم يتم العثور على DISCORD_TOKEN في .env")
                break
        except Exception as e:
            log_error("BOT_CRASH", str(e))
            time.sleep(60)
