
import asyncio
import json
import os
import time
import random
import string
from datetime import datetime, timedelta
from telethon import TelegramClient, events, types, Button, functions
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from collections import deque
import threading

# ===== الإعدادات =====
BOT_TOKEN = "5876070267:AAEN89CArFut-2ObR2BpbT5Oq4QhQQX3Jww"
D7_BOT_USERNAME = "D7Bot"
CONFIG_FILE = "userbot_config.json"
CODES_FILE = "codes_database.json"
QUEUE_FILE = "operations_queue.json"

# إعدادات الأدمن
ADMIN_ID = 5841353971  # ID الأدمن الجديد
DEFAULT_ACCESS_DURATION_HOURS = 24  # مدة الوصول الافتراضية بالساعات

# نظام منع التضارب
operation_queue = deque()
queue_lock = threading.Lock()
is_processing = False

ADMIN_RIGHTS = types.ChatAdminRights(
    change_info=True,
    post_messages=True,
    edit_messages=True,
    delete_messages=True,
    ban_users=True,
    invite_users=True,
    pin_messages=True,
    add_admins=True,
    manage_call=True,
    other=True,
    anonymous=False
)

# ===== نظام الطابور لمنع التضارب =====
def save_queue():
    """حفظ الطابور في ملف"""
    try:
        with open(QUEUE_FILE, "w") as f:
            json.dump(list(operation_queue), f)
    except:
        pass

def load_queue():
    """تحميل الطابور من ملف"""
    global operation_queue
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r") as f:
                data = json.load(f)
                operation_queue = deque(data)
        except:
            operation_queue = deque()

def add_to_queue(operation):
    """إضافة عملية للطابور"""
    with queue_lock:
        operation_queue.append(operation)
        save_queue()

def get_next_operation():
    """الحصول على العملية التالية"""
    with queue_lock:
        if operation_queue:
            operation = operation_queue.popleft()
            save_queue()
            return operation
    return None

def get_queue_position(user_id):
    """الحصول على موقع المستخدم في الطابور"""
    with queue_lock:
        for i, op in enumerate(operation_queue):
            if op.get('user_id') == user_id:
                return i + 1
    return 0

# ===== حفظ واسترجاع إعدادات Userbot =====
def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {"accounts": [], "group_settings": {"custom_name": "", "custom_description": "مرحباً بالجميع", "custom_message": "ايدي", "delay_between_groups": 5}}
    return {"accounts": [], "group_settings": {"custom_name": "", "custom_description": "مرحباً بالجميع", "custom_message": "ايدي", "delay_between_groups": 5}}

# ===== إدارة الأكواد المؤقتة =====
def save_codes_db(data):
    with open(CODES_FILE, "w") as f:
        json.dump(data, f)

def load_codes_db():
    if os.path.exists(CODES_FILE):
        try:
            with open(CODES_FILE, "r") as f:
                return json.load(f)
        except:
            return {"codes": {}, "user_access": {}, "user_stats": {}, "daily_limits": {}}
    return {"codes": {}, "user_access": {}, "user_stats": {}, "daily_limits": {}}

def generate_random_code():
    """توليد كود عشوائي من 6 أحرف وأرقام"""
    chars = string.ascii_uppercase + string.digits  # A-Z + 0-9
    return ''.join(random.choices(chars, k=6))

def create_new_code(duration_hours=None):
    """إنشاء كود جديد وحفظه في قاعدة البيانات مع مدة مخصصة"""
    codes_db = load_codes_db()
    new_code = generate_random_code()
    
    # التأكد من أن الكود غير مستخدم
    while new_code in codes_db["codes"]:
        new_code = generate_random_code()
    
    # استخدام المدة المخصصة أو الافتراضية
    if duration_hours is None:
        duration_hours = DEFAULT_ACCESS_DURATION_HOURS
    
    # حفظ الكود مع حالة "غير مستخدم" والمدة المخصصة
    codes_db["codes"][new_code] = {
        "used": False,
        "created_at": datetime.now().isoformat(),
        "duration_hours": duration_hours
    }
    
    save_codes_db(codes_db)
    return new_code, duration_hours

def use_code(code, user_id):
    """استخدام الكود ومنح الوصول للمستخدم"""
    codes_db = load_codes_db()
    
    if code not in codes_db["codes"]:
        return False, "كود غير صحيح"
    
    if codes_db["codes"][code]["used"]:
        return False, "الكود مستخدم مسبقاً"
    
    # الحصول على مدة الوصول من الكود أو استخدام المدة الافتراضية
    code_data = codes_db["codes"][code]
    duration_hours = code_data.get("duration_hours", DEFAULT_ACCESS_DURATION_HOURS)
    
    # إضافة المدة الافتراضية للأكواد القديمة
    if "duration_hours" not in code_data:
        codes_db["codes"][code]["duration_hours"] = DEFAULT_ACCESS_DURATION_HOURS
        duration_hours = DEFAULT_ACCESS_DURATION_HOURS
    
    # تحديد وقت انتهاء الوصول
    expiry_time = datetime.now() + timedelta(hours=duration_hours)
    
    # منح الوصول للمستخدم
    codes_db["user_access"][str(user_id)] = {
        "granted_at": datetime.now().isoformat(),
        "expires_at": expiry_time.isoformat(),
        "code_used": code,
        "duration_hours": duration_hours
    }
    
    # إحصائيات المستخدم
    if str(user_id) not in codes_db["user_stats"]:
        codes_db["user_stats"][str(user_id)] = {"groups_created": 0, "last_activity": ""}
    
    # تحديد الكود كمستخدم
    codes_db["codes"][code]["used"] = True
    codes_db["codes"][code]["used_by"] = user_id
    codes_db["codes"][code]["used_at"] = datetime.now().isoformat()
    
    save_codes_db(codes_db)
    return True, f"تم منح الوصول لمدة {duration_hours} ساعة"

def check_user_access(user_id):
    """فحص صلاحية وصول المستخدم"""
    codes_db = load_codes_db()
    user_str = str(user_id)
    
    if user_str not in codes_db["user_access"]:
        return False, "لا يوجد وصول"
    
    user_data = codes_db["user_access"][user_str]
    expiry_time = datetime.fromisoformat(user_data["expires_at"])
    
    if datetime.now() > expiry_time:
        # انتهت صلاحية الوصول
        del codes_db["user_access"][user_str]
        save_codes_db(codes_db)
        return False, "انتهت صلاحية الوصول"
    
    return True, "وصول صالح"

def check_daily_limit(user_id, requested_groups):
    """فحص الحد اليومي للمستخدم"""
    codes_db = load_codes_db()
    user_str = str(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if "daily_limits" not in codes_db:
        codes_db["daily_limits"] = {}
    
    if user_str not in codes_db["daily_limits"]:
        codes_db["daily_limits"][user_str] = {}
    
    if today not in codes_db["daily_limits"][user_str]:
        codes_db["daily_limits"][user_str][today] = 0
    
    current_usage = codes_db["daily_limits"][user_str][today]
    daily_limit = 100  # حد يومي 100 مجموعة للمستخدم العادي
    
    if user_id == ADMIN_ID:
        daily_limit = 1000  # حد أعلى للأدمن
    
    if current_usage + requested_groups > daily_limit:
        return False, f"تجاوزت الحد اليومي! استخدمت {current_usage}/{daily_limit} مجموعة اليوم"
    
    return True, "ضمن الحد المسموح"

def update_daily_usage(user_id, groups_created):
    """تحديث الاستخدام اليومي"""
    codes_db = load_codes_db()
    user_str = str(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if "daily_limits" not in codes_db:
        codes_db["daily_limits"] = {}
    
    if user_str not in codes_db["daily_limits"]:
        codes_db["daily_limits"][user_str] = {}
    
    if today not in codes_db["daily_limits"][user_str]:
        codes_db["daily_limits"][user_str][today] = 0
    
    codes_db["daily_limits"][user_str][today] += groups_created
    
    # تحديث إحصائيات المستخدم
    if "user_stats" not in codes_db:
        codes_db["user_stats"] = {}
    
    if user_str not in codes_db["user_stats"]:
        codes_db["user_stats"][user_str] = {"groups_created": 0, "last_activity": ""}
    
    codes_db["user_stats"][user_str]["groups_created"] += groups_created
    codes_db["user_stats"][user_str]["last_activity"] = datetime.now().isoformat()
    
    save_codes_db(codes_db)

def get_user_access_info(user_id):
    """الحصول على معلومات وصول المستخدم"""
    codes_db = load_codes_db()
    user_str = str(user_id)
    
    if user_str in codes_db["user_access"]:
        user_data = codes_db["user_access"][user_str]
        expiry_time = datetime.fromisoformat(user_data["expires_at"])
        remaining_time = expiry_time - datetime.now()
        
        if remaining_time.total_seconds() > 0:
            hours = int(remaining_time.total_seconds() // 3600)
            minutes = int((remaining_time.total_seconds() % 3600) // 60)
            
            # إحصائيات إضافية
            today = datetime.now().strftime("%Y-%m-%d")
            daily_usage = codes_db.get("daily_limits", {}).get(user_str, {}).get(today, 0)
            total_groups = codes_db.get("user_stats", {}).get(user_str, {}).get("groups_created", 0)
            
            info = f"⏰ الوقت المتبقي: {hours} ساعة و {minutes} دقيقة\n"
            info += f"📊 استخدام اليوم: {daily_usage}/100 مجموعة\n"
            info += f"🔢 إجمالي المجموعات: {total_groups}"
            return info
    
    return "❌ لا يوجد وصول صالح"

def get_detailed_bot_stats():
    """الحصول على إحصائيات شاملة للبوت"""
    codes_db = load_codes_db()
    config = load_config()
    
    # إحصائيات الأكواد
    total_codes = len(codes_db["codes"])
    used_codes = sum(1 for code_data in codes_db["codes"].values() if code_data["used"])
    unused_codes = total_codes - used_codes
    
    # إحصائيات المستخدمين
    total_users = len(codes_db["user_access"])
    active_users = 0
    expired_users = 0
    
    # فحص المستخدمين النشطين
    current_time = datetime.now()
    for user_data in codes_db["user_access"].values():
        expiry_time = datetime.fromisoformat(user_data["expires_at"])
        if current_time < expiry_time:
            active_users += 1
        else:
            expired_users += 1
    
    # إحصائيات المجموعات الحقيقية
    total_groups_created = sum(
        stats.get("groups_created", 0) 
        for stats in codes_db.get("user_stats", {}).values()
    )
    
    # إحصائيات الحسابات
    total_accounts = len(config.get("accounts", []))
    
    # إحصائيات الطابور
    queue_size = len(operation_queue)
    
    return {
        "codes": {
            "total": total_codes,
            "used": used_codes,
            "unused": unused_codes
        },
        "users": {
            "total": total_users,
            "active": active_users,
            "expired": expired_users
        },
        "accounts": total_accounts,
        "groups_created": total_groups_created,
        "queue_size": queue_size
    }

# ===== تنظيف ملفات الجلسة المقفلة =====
def cleanup_locked_sessions():
    for file in os.listdir('.'):
        if file.endswith('.session-journal'):
            try:
                os.remove(file)
                print(f"[+] حذف ملف مقفل: {file}")
            except:
                pass

# ===== تسجيل حساب جديد =====
async def setup_account_via_bot(conv):
    await conv.send_message("📲 أرسل رقم الهاتف (مثال +96477xxxxxxx):")
    msg = await conv.get_response()
    phone = msg.text.strip()

    await conv.send_message("🔑 أدخل API ID:")
    msg = await conv.get_response()
    try:
        api_id = int(msg.text.strip())
    except:
        await conv.send_message("❌ API ID يجب أن يكون رقم!")
        return

    await conv.send_message("🛡️ أدخل API HASH:")
    msg = await conv.get_response()
    api_hash = msg.text.strip()

    session_file = f"userbot_{phone.replace('+', '').replace(' ', '')}.session"
    
    # تنظيف الجلسة القديمة
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
        except:
            pass
    
    cleanup_locked_sessions()
    
    try:
        client = TelegramClient(session_file, api_id, api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            await conv.send_message("📩 أدخل كود التحقق المرسل لك:")
            code_msg = await conv.get_response()
            code = code_msg.text.strip()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                await conv.send_message("🔑 أدخل كلمة المرور 2FA:")
                pwd_msg = await conv.get_response()
                password = pwd_msg.text.strip()
                await client.sign_in(password=password)

        # حفظ الحساب في config
        config = load_config()
        
        # إضافة الحساب الجديد بدلاً من استبدال القائمة
        new_account = {
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "session": session_file
        }
        
        # فحص إذا كان الحساب موجود مسبقاً
        account_exists = False
        for i, account in enumerate(config["accounts"]):
            if account["phone"] == phone:
                config["accounts"][i] = new_account
                account_exists = True
                break
        
        if not account_exists:
            config["accounts"].append(new_account)
        
        save_config(config)
        await conv.send_message(f"✅ تم تسجيل Userbot وحفظ الجلسة: {session_file}")
        await client.disconnect()
    except Exception as e:
        await conv.send_message(f"❌ خطأ في تسجيل الحساب: {str(e)}")

# ===== إنشاء قروب =====
async def create_supergroup(client, title, group_num, total_groups, custom_description="مرحباً بالجميع", custom_message="ايدي"):
    try:
        result = await client(functions.channels.CreateChannelRequest(
            title=title,
            about=custom_description,
            megagroup=True
        ))
        channel = result.chats[0]
        print(f"[+] تم إنشاء المجموعة {group_num}/{total_groups}: {title}")
        
        # انتظار قصير بعد إنشاء المجموعة
        await asyncio.sleep(2)

        # إضافة D7Bot كأدمن
        try:
            d7 = await client.get_entity(D7_BOT_USERNAME)
            await client(functions.channels.EditAdminRequest(
                channel=channel,
                user_id=d7,
                admin_rights=ADMIN_RIGHTS,
                rank="Admin"
            ))
            print(f"[+] تم إضافة @{D7_BOT_USERNAME} كأدمن في {title}")
        except Exception as e:
            print(f"[!] خطأ إضافة @{D7_BOT_USERNAME} كأدمن: {e}")

        # إرسال 7 رسائل مخصصة
        for i in range(7):
            try:
                await client.send_message(channel, custom_message)
                await asyncio.sleep(1)  # انتظار ثانية بين كل رسالة
            except Exception as e:
                print(f"[!] خطأ إرسال الرسالة {i+1}: {e}")

        return True
        
    except FloodWaitError as e:
        print(f"[!] مطلوب انتظار {e.seconds} ثانية لإنشاء المجموعات")
        hours = e.seconds // 3600
        minutes = (e.seconds % 3600) // 60
        return f"❌ مطلوب انتظار {hours} ساعة و {minutes} دقيقة قبل إنشاء مجموعات جديدة"
    except Exception as e:
        print(f"[!] خطأ في إنشاء المجموعة {title}: {e}")
        return False

# ===== معالج الطابور =====
async def process_queue():
    """معالجة الطابور بشكل تسلسلي"""
    global is_processing
    
    while True:
        try:
            if not is_processing and operation_queue:
                is_processing = True
                operation = get_next_operation()
                
                if operation:
                    await execute_operation(operation)
                
                is_processing = False
            
            await asyncio.sleep(1)  # فحص كل ثانية
        except Exception as e:
            print(f"خطأ في معالجة الطابور: {e}")
            is_processing = False

async def execute_operation(operation):
    """تنفيذ عملية من الطابور"""
    try:
        op_type = operation["type"]
        user_id = operation["user_id"]
        
        if op_type == "create_groups":
            count = operation["count"]
            config = load_config()
            
            if not config["accounts"]:
                return
            
            # اختيار حساب نشط
            active_account = None
            for account in config["accounts"]:
                try:
                    client = TelegramClient(account["session"], account["api_id"], account["api_hash"])
                    await client.connect()
                    if await client.is_user_authorized():
                        active_account = account
                        await client.disconnect()
                        break
                    await client.disconnect()
                except:
                    continue
            
            if not active_account:
                return
            
            # تنفيذ إنشاء المجموعات
            cleanup_locked_sessions()
            client = TelegramClient(active_account["session"], active_account["api_id"], active_account["api_hash"])
            await client.start(phone=active_account["phone"])
            
            success_count = 0
            group_settings = config.get("group_settings", {})
            custom_name = group_settings.get("custom_name", "")
            custom_description = group_settings.get("custom_description", "مرحباً بالجميع")
            custom_message = group_settings.get("custom_message", "ايدي")
            delay = group_settings.get("delay_between_groups", 5)
            
            for i in range(1, count + 1):
                title = f"{custom_name} #{i}" if custom_name else f"Group #{i}"
                
                result = await create_supergroup(
                    client, title, i, count, 
                    custom_description, custom_message
                )
                
                if result == True:
                    success_count += 1
                elif isinstance(result, str):  # FloodWaitError
                    break
                
                if i < count:
                    await asyncio.sleep(delay)
            
            await client.disconnect()
            
            # تحديث الإحصائيات
            if success_count > 0:
                update_daily_usage(user_id, success_count)
            
    except Exception as e:
        print(f"خطأ في تنفيذ العملية: {e}")

# ===== Main =====
async def main():
    # تحميل الطابور
    load_queue()
    
    # تنظيف الجلسات المقفلة
    cleanup_locked_sessions()
    
    # حذف ملف جلسة البوت إذا كان موجوداً
    if os.path.exists("bot_session.session"):
        try:
            os.remove("bot_session.session")
        except:
            pass
    
    bot_client = TelegramClient("bot_session", 29885460, "9fece1c7f0ebf1526ed9ade4cb455a03")
    await bot_client.start(bot_token=BOT_TOKEN)

    # بدء معالج الطابور
    asyncio.create_task(process_queue())

    @bot_client.on(events.NewMessage(pattern="/start"))
    async def start_handler(event):
        user_id = event.sender_id
        
        # فحص إذا كان المستخدم أدمن
        if user_id == ADMIN_ID:
            config = load_config()
            buttons = [[Button.inline("إضافة حساب جديد", b"add_account")]]
            buttons.append([Button.inline("عرض الحسابات", b"show_accounts")])
            buttons.append([Button.inline("🎫 توليد كود (مدة مخصصة)", b"generate_code_custom")])
            buttons.append([Button.inline("🎫 توليد كود سريع (24 ساعة)", b"generate_code")])
            buttons.append([Button.inline("📊 إحصائيات الأكواد", b"codes_stats")])
            buttons.append([Button.inline("📈 إحصائيات البوت الشاملة", b"bot_stats")])
            buttons.append([Button.inline("🗑️ حذف المجموعات", b"delete_groups")])
            buttons.append([Button.inline("📦 نقل المجموعات", b"transfer_groups")])
            buttons.append([Button.inline("⚙️ إعدادات المجموعات", b"group_settings")])
            buttons.append([Button.inline("📋 عرض الطابور", b"view_queue")])
            buttons.append([Button.inline("5", b"5"), Button.inline("10", b"10")])
            buttons.append([Button.inline("15", b"15"), Button.inline("20", b"20")])
            buttons.append([Button.inline("50", b"50"), Button.inline("100", b"100")])
            
            welcome_text = "👑 مرحباً أدمن! اختر الإجراء المطلوب:"
            await event.respond(welcome_text, buttons=buttons)
        else:
            # فحص وصول المستخدم أولاً
            has_access, message = check_user_access(user_id)
            
            if has_access:
                # المستخدم لديه وصول صالح
                config = load_config()
                buttons = [[Button.inline("إضافة حساب جديد", b"add_account")]]
                buttons.append([Button.inline("5", b"5"), Button.inline("10", b"10")])
                buttons.append([Button.inline("15", b"15"), Button.inline("20", b"20")])
                buttons.append([Button.inline("50", b"50")])
                buttons.append([Button.inline("⏰ معلومات الحساب", b"check_time")])
                buttons.append([Button.inline("📊 موقعي في الطابور", b"queue_position")])
                
                welcome_text = "✅ مرحباً! اختر عدد المجموعات التي تريد إنشاؤها:"
                await event.respond(welcome_text, buttons=buttons)
            else:
                # طلب الكود من المستخدم
                await event.respond("🔑 أدخل الكود للوصول للبوت:")

    @bot_client.on(events.NewMessage)
    async def code_handler(event):
        user_id = event.sender_id
        
        # تجاهل الأوامر والأدمن
        if event.text.startswith('/') or user_id == ADMIN_ID:
            return
        
        # فحص إذا كان المستخدم لديه وصول بالفعل
        has_access, _ = check_user_access(user_id)
        if has_access:
            return
            
        # فحص الكود
        code = event.text.strip().upper()  # تحويل لأحرف كبيرة للتوافق
        if len(code) == 6 and code.isalnum():  # يقبل أحرف وأرقام
            success, message = use_code(code, user_id)
            
            if success:
                config = load_config()
                buttons = [[Button.inline("إضافة حساب جديد", b"add_account")]]
                buttons.append([Button.inline("5", b"5"), Button.inline("10", b"10")])
                buttons.append([Button.inline("15", b"15"), Button.inline("20", b"20")])
                buttons.append([Button.inline("50", b"50")])
                buttons.append([Button.inline("⏰ معلومات الحساب", b"check_time")])
                buttons.append([Button.inline("📊 موقعي في الطابور", b"queue_position")])
                
                welcome_text = f"✅ {message}\n\nاختر عدد المجموعات التي تريد إنشاؤها:"
                await event.respond(welcome_text, buttons=buttons)
            else:
                await event.respond(f"❌ {message}")
        elif len(code) == 6:
            await event.respond("❌ كود خاطئ! حاول مرة أخرى:")

    @bot_client.on(events.CallbackQuery)
    async def callback_handler(event):
        async with bot_client.conversation(event.sender_id) as conv:
            if event.data == b"add_account":
                await event.answer()
                await setup_account_via_bot(conv)
            
            elif event.data == b"show_accounts":
                config = load_config()
                if config["accounts"]:
                    accounts_text = "📱 الحسابات المحفوظة:\n\n"
                    for i, account in enumerate(config["accounts"], 1):
                        # فحص حالة الحساب
                        status = "❓ غير محقق"
                        try:
                            client = TelegramClient(account["session"], account["api_id"], account["api_hash"])
                            await client.connect()
                            if await client.is_user_authorized():
                                status = "✅ نشط"
                            else:
                                status = "❌ غير مفعل"
                            await client.disconnect()
                        except:
                            status = "❌ خطأ"
                        
                        accounts_text += f"{i}. {account['phone']} - {status}\n"
                else:
                    accounts_text = "❌ لا توجد حسابات محفوظة"
                await conv.send_message(accounts_text)
                await event.answer()
            
            elif event.data == b"generate_code":
                new_code, duration = create_new_code()
                await conv.send_message(f"🎫 تم توليد كود سريع:\n\n`{new_code}`\n\n⚠️ الكود يستخدم مرة واحدة فقط\n⏰ مدة الوصول: {duration} ساعة")
                await event.answer()
            
            elif event.data == b"generate_code_custom":
                await conv.send_message("⏰ أدخل عدد الساعات للوصول (مثال: 12, 48, 168):")
                hours_msg = await conv.get_response()
                try:
                    custom_hours = int(hours_msg.text.strip())
                    if custom_hours <= 0:
                        await conv.send_message("❌ عدد الساعات يجب أن يكون أكبر من صفر!")
                        return
                    
                    new_code, duration = create_new_code(custom_hours)
                    await conv.send_message(f"🎫 تم توليد كود مخصص:\n\n`{new_code}`\n\n⚠️ الكود يستخدم مرة واحدة فقط\n⏰ مدة الوصول: {duration} ساعة\n📅 تاريخ الانتهاء: {(datetime.now() + timedelta(hours=duration)).strftime('%Y-%m-%d %H:%M')}")
                except ValueError:
                    await conv.send_message("❌ يرجى إدخال رقم صحيح للساعات!")
                await event.answer()
            
            elif event.data == b"codes_stats":
                codes_db = load_codes_db()
                total_codes = len(codes_db["codes"])
                used_codes = sum(1 for code_data in codes_db["codes"].values() if code_data["used"])
                active_users = 0
                
                # فحص المستخدمين النشطين
                current_time = datetime.now()
                for user_data in codes_db["user_access"].values():
                    expiry_time = datetime.fromisoformat(user_data["expires_at"])
                    if current_time < expiry_time:
                        active_users += 1
                
                stats_text = f"📊 إحصائيات الأكواد:\n\n"
                stats_text += f"🎫 إجمالي الأكواد: {total_codes}\n"
                stats_text += f"✅ أكواد مستخدمة: {used_codes}\n"
                stats_text += f"🆕 أكواد متاحة: {total_codes - used_codes}\n"
                stats_text += f"👥 مستخدمين نشطين: {active_users}\n"
                stats_text += f"⏰ مدة الوصول الافتراضية: {DEFAULT_ACCESS_DURATION_HOURS} ساعة"
                
                await conv.send_message(stats_text)
                await event.answer()
            
            elif event.data == b"bot_stats":
                stats = get_detailed_bot_stats()
                
                stats_text = f"📈 إحصائيات البوت الشاملة:\n\n"
                stats_text += f"🎫 **الأكواد:**\n"
                stats_text += f"   • إجمالي: {stats['codes']['total']}\n"
                stats_text += f"   • مستخدمة: {stats['codes']['used']}\n"
                stats_text += f"   • متاحة: {stats['codes']['unused']}\n\n"
                
                stats_text += f"👥 **المستخدمين:**\n"
                stats_text += f"   • إجمالي: {stats['users']['total']}\n"
                stats_text += f"   • نشطين: {stats['users']['active']}\n"
                stats_text += f"   • منتهي الصلاحية: {stats['users']['expired']}\n\n"
                
                stats_text += f"📱 **الحسابات المحفوظة:** {stats['accounts']}\n"
                stats_text += f"🔢 **المجموعات المُنشأة:** {stats['groups_created']}\n"
                stats_text += f"⏳ **الطابور الحالي:** {stats['queue_size']} عملية\n\n"
                stats_text += f"📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                
                await conv.send_message(stats_text)
                await event.answer()
            
            elif event.data == b"check_time":
                user_id = event.sender_id
                time_info = get_user_access_info(user_id)
                await conv.send_message(time_info)
                await event.answer()
            
            elif event.data == b"queue_position":
                user_id = event.sender_id
                position = get_queue_position(user_id)
                if position > 0:
                    queue_info = f"📊 موقعك في الطابور: #{position}\n"
                    queue_info += f"⏳ العمليات المنتظرة: {len(operation_queue)}\n"
                    queue_info += f"🔄 حالة المعالجة: {'جاري التنفيذ' if is_processing else 'في الانتظار'}"
                else:
                    queue_info = "✅ لا توجد عمليات منتظرة لك في الطابور"
                
                await conv.send_message(queue_info)
                await event.answer()
            
            elif event.data == b"view_queue":
                if event.sender_id != ADMIN_ID:
                    await event.answer("❌ غير مسموح")
                    return
                
                if operation_queue:
                    queue_text = f"📋 الطابور الحالي ({len(operation_queue)} عملية):\n\n"
                    for i, op in enumerate(list(operation_queue)[:10], 1):  # عرض أول 10 عمليات
                        queue_text += f"{i}. المستخدم {op['user_id']} - {op['type']}"
                        if op['type'] == 'create_groups':
                            queue_text += f" ({op['count']} مجموعة)"
                        queue_text += "\n"
                    
                    if len(operation_queue) > 10:
                        queue_text += f"... و {len(operation_queue) - 10} عملية أخرى"
                else:
                    queue_text = "✅ الطابور فارغ"
                
                await conv.send_message(queue_text)
                await event.answer()
            
            elif event.data == b"group_settings":
                if event.sender_id != ADMIN_ID:
                    await event.answer("❌ غير مسموح")
                    return
                
                config = load_config()
                settings = config.get("group_settings", {})
                
                settings_text = f"⚙️ إعدادات المجموعات الحالية:\n\n"
                settings_text += f"📝 اسم مخصص: {settings.get('custom_name', 'افتراضي')}\n"
                settings_text += f"📄 الوصف: {settings.get('custom_description', 'مرحباً بالجميع')}\n"
                settings_text += f"💬 الرسالة: {settings.get('custom_message', 'ايدي')}\n"
                settings_text += f"⏱️ التأخير: {settings.get('delay_between_groups', 5)} ثانية\n\n"
                settings_text += "اختر ما تريد تغييره:"
                
                buttons = [
                    [Button.inline("📝 تغيير الاسم", b"change_name")],
                    [Button.inline("📄 تغيير الوصف", b"change_description")],
                    [Button.inline("💬 تغيير الرسالة", b"change_message")],
                    [Button.inline("⏱️ تغيير التأخير", b"change_delay")]
                ]
                
                await conv.send_message(settings_text, buttons=buttons)
                await event.answer()
            
            elif event.data == b"change_name":
                await conv.send_message("📝 أدخل الاسم المخصص للمجموعات (أو 'افتراضي' للعودة للاسم الافتراضي):")
                name_msg = await conv.get_response()
                new_name = name_msg.text.strip()
                
                config = load_config()
                if "group_settings" not in config:
                    config["group_settings"] = {}
                
                if new_name.lower() == "افتراضي":
                    config["group_settings"]["custom_name"] = ""
                    await conv.send_message("✅ تم العودة للاسم الافتراضي")
                else:
                    config["group_settings"]["custom_name"] = new_name
                    await conv.send_message(f"✅ تم تحديث الاسم إلى: {new_name}")
                
                save_config(config)
                await event.answer()
            
            elif event.data == b"change_description":
                await conv.send_message("📄 أدخل الوصف الجديد للمجموعات:")
                desc_msg = await conv.get_response()
                new_desc = desc_msg.text.strip()
                
                config = load_config()
                if "group_settings" not in config:
                    config["group_settings"] = {}
                
                config["group_settings"]["custom_description"] = new_desc
                save_config(config)
                
                await conv.send_message(f"✅ تم تحديث الوصف إلى: {new_desc}")
                await event.answer()
            
            elif event.data == b"change_message":
                await conv.send_message("💬 أدخل الرسالة الجديدة التي ستُرسل في المجموعات:")
                msg_msg = await conv.get_response()
                new_message = msg_msg.text.strip()
                
                config = load_config()
                if "group_settings" not in config:
                    config["group_settings"] = {}
                
                config["group_settings"]["custom_message"] = new_message
                save_config(config)
                
                await conv.send_message(f"✅ تم تحديث الرسالة إلى: {new_message}")
                await event.answer()
            
            elif event.data == b"change_delay":
                await conv.send_message("⏱️ أدخل وقت التأخير بين المجموعات (بالثواني):")
                delay_msg = await conv.get_response()
                try:
                    new_delay = int(delay_msg.text.strip())
                    if new_delay < 1:
                        await conv.send_message("❌ وقت التأخير يجب أن يكون أكبر من صفر!")
                        return
                    
                    config = load_config()
                    if "group_settings" not in config:
                        config["group_settings"] = {}
                    
                    config["group_settings"]["delay_between_groups"] = new_delay
                    save_config(config)
                    
                    await conv.send_message(f"✅ تم تحديث وقت التأخير إلى: {new_delay} ثانية")
                except ValueError:
                    await conv.send_message("❌ يرجى إدخال رقم صحيح!")
                await event.answer()
            
            elif event.data == b"delete_groups":
                config = load_config()
                if not config["accounts"]:
                    await conv.send_message("❌ سجل دخول Userbot أولاً.")
                    await event.answer()
                    return
                
                await conv.send_message("🗑️ كم مجموعة تريد حذف؟ (أدخل رقم):")
                count_msg = await conv.get_response()
                try:
                    delete_count = int(count_msg.text.strip())
                    if delete_count <= 0:
                        await conv.send_message("❌ عدد المجموعات يجب أن يكون أكبر من صفر!")
                        return
                        
                    await conv.send_message(f"⚠️ متأكد من حذف {delete_count} مجموعة؟ اكتب 'نعم' للتأكيد:")
                    confirm_msg = await conv.get_response()
                    
                    if confirm_msg.text.strip().lower() in ['نعم', 'yes', 'موافق']:
                        # إضافة العملية للطابور
                        operation = {
                            "type": "delete_groups",
                            "user_id": event.sender_id,
                            "count": delete_count,
                            "timestamp": datetime.now().isoformat()
                        }
                        add_to_queue(operation)
                        
                        position = get_queue_position(event.sender_id)
                        await conv.send_message(f"✅ تم إضافة عملية الحذف للطابور\n📊 موقعك: #{position}")
                    else:
                        await conv.send_message("❌ تم إلغاء عملية الحذف")
                        
                except ValueError:
                    await conv.send_message("❌ يرجى إدخال رقم صحيح!")
                await event.answer()
            
            elif event.data == b"transfer_groups":
                config = load_config()
                if not config["accounts"]:
                    await conv.send_message("❌ سجل دخول Userbot أولاً.")
                    await event.answer()
                    return
                
                await conv.send_message("📦 أدخل username الحساب المستقبل (بدون @):")
                username_msg = await conv.get_response()
                target_username = username_msg.text.strip().replace('@', '')
                
                await conv.send_message("🔢 كم مجموعة تريد نقل؟ (أدخل رقم):")
                count_msg = await conv.get_response()
                try:
                    transfer_count = int(count_msg.text.strip())
                    if transfer_count <= 0:
                        await conv.send_message("❌ عدد المجموعات يجب أن يكون أكبر من صفر!")
                        return
                    
                    # إضافة العملية للطابور
                    operation = {
                        "type": "transfer_groups",
                        "user_id": event.sender_id,
                        "count": transfer_count,
                        "target_username": target_username,
                        "timestamp": datetime.now().isoformat()
                    }
                    add_to_queue(operation)
                    
                    position = get_queue_position(event.sender_id)
                    await conv.send_message(f"✅ تم إضافة عملية النقل للطابور\n📊 موقعك: #{position}\n👤 المستقبل: @{target_username}")
                        
                except ValueError:
                    await conv.send_message("❌ يرجى إدخال رقم صحيح!")
                await event.answer()

            elif event.data in [b"5", b"10", b"15", b"20", b"50", b"100"]:
                user_id = event.sender_id
                
                # فحص الوصول للمستخدمين العاديين
                if user_id != ADMIN_ID:
                    has_access, message = check_user_access(user_id)
                    if not has_access:
                        await conv.send_message("❌ انتهت صلاحية الوصول. احصل على كود جديد من الأدمن.")
                        await event.answer()
                        return
                
                count = int(event.data.decode())
                
                # فحص الحد اليومي
                if user_id != ADMIN_ID:
                    can_create, limit_message = check_daily_limit(user_id, count)
                    if not can_create:
                        await conv.send_message(f"❌ {limit_message}")
                        await event.answer()
                        return
                
                config = load_config()
                
                if not config["accounts"]:
                    await conv.send_message("❌ سجل دخول Userbot أولاً.")
                    return

                # إضافة العملية للطابور
                operation = {
                    "type": "create_groups",
                    "user_id": user_id,
                    "count": count,
                    "timestamp": datetime.now().isoformat()
                }
                add_to_queue(operation)
                
                position = get_queue_position(user_id)
                queue_msg = f"✅ تم إضافة طلب إنشاء {count} مجموعة للطابور\n"
                queue_msg += f"📊 موقعك في الطابور: #{position}\n"
                queue_msg += f"⏳ العمليات المنتظرة: {len(operation_queue)}\n"
                queue_msg += f"🔄 حالة المعالجة: {'جاري التنفيذ' if is_processing else 'في الانتظار'}\n\n"
                queue_msg += "📝 ملاحظة: ستبدأ عمليتك تلقائياً عند وصول دورك"
                
                await conv.send_message(queue_msg)

    print("[*] البوت جاهز! ارسل /start في تليجرام.")
    await bot_client.run_until_disconnected()

# توليد كود جديد للمستخدم
def generate_code_for_user():
    new_code, duration = create_new_code()
    print(f"🎫 كود جديد: {new_code}")
    print(f"⏰ مدة الوصول: {duration} ساعة")
    return new_code

# توليد كود للمستخدم قبل تشغيل البوت
print("=" * 50)
user_code = generate_code_for_user()
print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
