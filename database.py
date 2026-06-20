import sqlite3
import os
import shutil
from datetime import datetime
from logger_config import log_action, log_error

DB_PATH = 'phantom_pro.db'
BACKUP_DIR = 'backups'

os.makedirs(BACKUP_DIR, exist_ok=True)

def init_db():
    """تهيئة قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # جداول الإعدادات
        cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                         (guild_id TEXT PRIMARY KEY, admin_roles TEXT, channel_id TEXT, 
                          log_channel TEXT, category_id TEXT, created_at TIMESTAMP)''')
        
        # جداول الردود التلقائية
        cursor.execute('''CREATE TABLE IF NOT EXISTS auto_replies 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT UNIQUE, 
                          response TEXT, created_at TIMESTAMP)''')
        
        # جداول المستويات والـ XP
        cursor.execute('''CREATE TABLE IF NOT EXISTS levels 
                         (user_id TEXT PRIMARY KEY, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, 
                          updated_at TIMESTAMP)''')
        
        # جداول اللوق (تسجيل العمليات)
        cursor.execute('''CREATE TABLE IF NOT EXISTS action_logs 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, user_id TEXT, 
                          details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # جداول التحذيرات
        cursor.execute('''CREATE TABLE IF NOT EXISTS warnings 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, guild_id TEXT, 
                          reason TEXT, warned_by TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # جداول البانات
        cursor.execute('''CREATE TABLE IF NOT EXISTS bans 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, guild_id TEXT, 
                          reason TEXT, banned_by TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        conn.commit()
        conn.close()
        log_action("DATABASE", "تم تهيئة قاعدة البيانات بنجاح")
    except Exception as e:
        log_error("DATABASE", f"خطأ في تهيئة قاعدة البيانات: {e}")

def backup_db():
    """نسخ احتياطي من قاعدة البيانات"""
    try:
        if os.path.exists(DB_PATH):
            backup_name = f"{BACKUP_DIR}/phantom_pro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy(DB_PATH, backup_name)
            log_action("BACKUP", f"تم النسخ الاحتياطي: {backup_name}")
            return True
    except Exception as e:
        log_error("BACKUP", str(e))
    return False

def log_action_db(action, user_id, details=""):
    """تسجيل إجراء في قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO action_logs (action, user_id, details, timestamp) 
                         VALUES (?, ?, ?, CURRENT_TIMESTAMP)''', 
                      (action, user_id, details))
        conn.commit()
        conn.close()
    except Exception as e:
        log_error("LOG_ACTION", str(e))

def add_warning(user_id, guild_id, reason, warned_by):
    """إضافة تحذير"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO warnings (user_id, guild_id, reason, warned_by, timestamp) 
                         VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)''', 
                      (user_id, guild_id, reason, warned_by))
        conn.commit()
        
        # الحصول على عدد التحذيرات
        cursor.execute('SELECT COUNT(*) FROM warnings WHERE user_id=? AND guild_id=?', 
                      (user_id, guild_id))
        count = cursor.fetchone()[0]
        conn.close()
        
        log_action_db("WARNING", user_id, f"تحذير جديد - السبب: {reason}")
        return count
    except Exception as e:
        log_error("ADD_WARNING", str(e))
    return 0

def get_warnings(user_id, guild_id):
    """الحصول على التحذيرات"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM warnings WHERE user_id=? AND guild_id=?', 
                      (user_id, guild_id))
        warnings = cursor.fetchall()
        conn.close()
        return warnings
    except Exception as e:
        log_error("GET_WARNINGS", str(e))
    return []

def add_ban(user_id, guild_id, reason, banned_by):
    """إضافة بان"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO bans (user_id, guild_id, reason, banned_by, timestamp) 
                         VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)''', 
                      (user_id, guild_id, reason, banned_by))
        conn.commit()
        conn.close()
        log_action_db("BAN", user_id, f"بان - السبب: {reason}")
        return True
    except Exception as e:
        log_error("ADD_BAN", str(e))
    return False

def is_user_banned(user_id, guild_id):
    """التحقق من البان"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM bans WHERE user_id=? AND guild_id=?', 
                      (user_id, guild_id))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        log_error("IS_BANNED", str(e))
    return False

init_db()
