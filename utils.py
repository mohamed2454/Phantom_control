import discord
import sqlite3
from logger_config import log_action, log_error

DB_PATH = 'phantom_pro.db'

def get_user_xp(user_id):
    """الحصول على XP المستخدم"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT xp, level FROM levels WHERE user_id=?', (str(user_id),))
        result = cursor.fetchone()
        conn.close()
        return result if result else (0, 1)
    except Exception as e:
        log_error("GET_XP", str(e))
    return (0, 1)

def calculate_level(xp):
    """حساب المستوى من الـ XP"""
    # كل 100 XP = مستوى واحد
    return (xp // 100) + 1

def get_level_progress(xp):
    """الحصول على تقدم المستوى الحالي"""
    current_level = calculate_level(xp)
    xp_for_next_level = current_level * 100
    xp_current_level = (current_level - 1) * 100
    progress = ((xp - xp_current_level) / (xp_for_next_level - xp_current_level)) * 100
    return min(progress, 100)

def create_xp_embed(user: discord.User, xp: int, level: int):
    """إنشاء Embed للـ XP"""
    embed = discord.Embed(
        title=f"📊 إحصائيات XP - {user.name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="المستوى", value=f"**{level}**", inline=True)
    embed.add_field(name="النقاط", value=f"**{xp}**", inline=True)
    progress = get_level_progress(xp)
    embed.add_field(name="التقدم", value=f"**{progress:.1f}%**", inline=False)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    return embed

def sanitize_input(text, max_length=1000):
    """تنظيف المدخلات"""
    if not text:
        return ""
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length]
    return text

def is_valid_channel_id(channel_id):
    """التحقق من صحة معرف القناة"""
    try:
        int(channel_id)
        return True
    except ValueError:
        return False

def is_valid_guild_id(guild_id):
    """التحقق من صحة معرف السيرفر"""
    try:
        int(guild_id)
        return True
    except ValueError:
        return False

def format_timestamp(timestamp):
    """تنسيق الطابع الزمني"""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp
