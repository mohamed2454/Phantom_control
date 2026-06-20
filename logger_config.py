import logging
import os
from datetime import datetime

# إنشاء مجلد logs إذا لم يكن موجوداً
os.makedirs('logs', exist_ok=True)

# إعداد نظام التسجيل
log_filename = f"logs/phantom_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def log_action(action, details=""):
    """تسجيل الإجراءات"""
    logger.info(f"[{action}] {details}")

def log_error(error, details=""):
    """تسجيل الأخطاء"""
    logger.error(f"[ERROR] {error} - {details}")

def log_warning(warning, details=""):
    """تسجيل التحذيرات"""
    logger.warning(f"[WARNING] {warning} - {details}")
