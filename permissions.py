import discord
from functools import wraps
from flask import request, jsonify

# قائمة المسؤولين (يمكن إضافة المزيد)
ADMIN_IDS = []

def is_admin_discord(user_id):
    """التحقق من كون المستخدم مسؤول Discord"""
    return int(user_id) in ADMIN_IDS

def is_admin_ip():
    """التحقق من عنوان IP المسموح"""
    # يمكن إضافة قائمة IPs المسموحة هنا
    allowed_ips = ['127.0.0.1', 'localhost']
    return request.remote_addr in allowed_ips

def require_admin(f):
    """Decorator للتحقق من صلاحيات المسؤول للـ Flask"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_ip():
            return jsonify({'error': 'غير مصرح لك بالوصول'}), 403
        return f(*args, **kwargs)
    return decorated_function

def check_guild_permissions(interaction: discord.Interaction, required_role=None):
    """التحقق من صلاحيات المستخدم في السيرفر"""
    if interaction.user == interaction.guild.owner:
        return True
    
    if required_role:
        return any(role.name == required_role for role in interaction.user.roles)
    
    return False

def validate_input(data, required_fields):
    """التحقق من المدخلات"""
    for field in required_fields:
        if field not in data or not data[field]:
            return False, f"الحقل '{field}' مطلوب"
    return True, "موافق"
