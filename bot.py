import re
import threading
from datetime import datetime

import psycopg2
import psycopg2.extras
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ===================== НАСТРОЙКИ =====================
TOKEN = "8972845479:AAFkpr9Bc0K2UBA8x3hZmobPlKLUK-4PKtA"           # ← ваш токен из @BotFather
ADMIN_IDS = [8621244180,740869889,8983954588]              # ← ваш Telegram ID
DATABASE_URL = "postgresql://postgres:[Sukasuka0003.]@db.vguziihdwdpkxngpwqrs.supabase.co:5432/postgres"  # ← строка из Supabase
# ===================== БАЗА ДАННЫХ =====================
def get_connection():
    return psycopg2.connect(DATABASE_URL)

# ===================== КЛАВИАТУРЫ =====================
main_kb = ReplyKeyboardMarkup([
    [KeyboardButton("🔍 Запросить историю")],
    [KeyboardButton("ℹ️ О сервисе"), KeyboardButton("📞 Контакты")]
], resize_keyboard=True)

admin_kb = ReplyKeyboardMarkup([
    [KeyboardButton("➕ Добавить автомобиль")],
    [KeyboardButton("🔧 Добавить обслуживание")],
    [KeyboardButton("📋 Все автомобили")],
    [KeyboardButton("🗑 Удалить автомобиль")],
    [KeyboardButton("🔍 Найти авто (админ)")],
    [KeyboardButton("❌ Выйти из админки")]
], resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup([
    [KeyboardButton("❌ Отмена")]
], resize_keyboard=True)

# ===================== СОСТОЯНИЯ =====================
(WAITING_QUERY, ADDING_CAR_VIN, ADDING_CAR_PLATE, ADDING_CAR_BRAND, 
 ADDING_CAR_MODEL, ADDING_CAR_YEAR, ADDING_CAR_CLIENT_NAME, 
 ADDING_CAR_CLIENT_PHONE, SELECTING_CAR, ADDING_SERVICE_DATE, 
 ADDING_SERVICE_MILEAGE, ADDING_SERVICE_DETAILS, DELETE_CAR_ID,
 DELETE_SERVICE_ID, SELECTING_CAR_FOR_DELETE) = range(15)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def detect_plate_country(plate: str) -> str:
    plate_clean = re.sub(r'\s+', '', plate.upper())
    if re.match(r'^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$', plate_clean):
        return "РФ"
    if re.match(r'^\d{2}KG\d{3}[A-Z]{3}$', plate_clean):
        return "Киргизия"
    if re.match(r'^\d{2}[A-Z]{2}\d{3}$', plate_clean):
        return "Армения"
    return "Неизвестно"

def search_car(query: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query_clean = re.sub(r'\s+', '', query.upper())
    cur.execute("SELECT * FROM cars WHERE UPPER(REPLACE(vin, ' ', '')) = %s OR UPPER(REPLACE(plate, ' ', '')) = %s",
                (query_clean, query_clean))
    car = cur.fetchone()
    cur.close()
    conn.close()
    return dict(car) if car else None

def get_services(car_id: int) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM services WHERE car_id = %s ORDER BY date DESC", (car_id,))
    services = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return services

def get_all_cars() -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM cars ORDER BY id DESC LIMIT 20")
    cars = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return cars

def get_car_by_id(car_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    car = cur.fetchone()
    cur.close()
    conn.close()
    return dict(car) if car else None

def format_services(services: list) -> str:
    if not services:
        return "📭 История обслуживания пуста"

    result = ""
    for s in services:
        parts = []
        parts.append(f"🆔 {s['id']} | 📅 <b>{s['date']}</b> | Пробег: <b>{s['mileage']:,} км</b>".replace(',', ' '))

        if s.get('other_work'):
            parts.append(f"🔧 <b>Работы:</b> {s['other_work']}")
        if s.get('master'):
            parts.append(f"👨‍🔧 Мастер: <b>{s['master']}</b>")
        if s.get('total_amount'):
            parts.append(f"💰 Сумма: <b>{s['total_amount']} ₽</b>")
        if s.get('notes'):
            parts.append(f"📝 <i>{s['notes']}</i>")

        result += "\n".join(parts) + "\n" + "─" * 25 + "\n"

    return result

async def safe_reply(update: Update, text: str, **kwargs):
    """Безопасная отправка сообщений"""
    try:
        return await update.message.reply_text(text, **kwargs)
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return None

# ===================== КОМАНДЫ =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await safe_reply(update,
            "👋 Добро пожаловать, администратор!\n\nВыберите действие в меню:",
            reply_markup=admin_kb
        )
    else:
        await safe_reply(update,
            "👋 Добро пожаловать в автосервис!\n\n"
            "Нажмите кнопку ниже, чтобы запросить историю обслуживания вашего автомобиля.",
            reply_markup=main_kb
        )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await safe_reply(update, "⛔ У вас нет доступа к админ-панели.")
        return
    await safe_reply(update, "🔐 Админ-панель активна.\nВыберите действие:", reply_markup=admin_kb)

# ===================== ЗАПРОС ИСТОРИИ =====================
async def request_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update,
        "Введите VIN-номер (17 символов) или госномер автомобиля:\n\n"
        "<i>Примеры:\n"
        "• РФ: А123БВ177 или А123БВ 177\n"
        "• Киргизия: 01KG123ABC\n"
        "• Армения: 12AB123</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    return WAITING_QUERY

async def process_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        kb = admin_kb if is_admin(update.effective_user.id) else main_kb
        await safe_reply(update, "❌ Запрос отменён.", reply_markup=kb)
        return ConversationHandler.END

    car = search_car(update.message.text.strip())
    if not car:
        await safe_reply(update,
            "❌ Автомобиль не найден.\nПроверьте VIN или госномер и попробуйте снова.",
            reply_markup=cancel_kb
        )
        return WAITING_QUERY

    services = get_services(car['id'])
    plate_str = f"{car['plate']} ({car['plate_country']})" if car['plate'] else "не указан"

    car_info = (
        f"🚗 <b>Автомобиль найден:</b>\n"
        f"📌 VIN: <code>{car['vin']}</code>\n"
        f"📋 Госномер: <b>{plate_str}</b>\n"
        f"🏷 Марка: <b>{car['brand'] or '—'}</b>\n"
        f"🚙 Модель: <b>{car['model'] or '—'}</b>\n"
        f"📅 Год: <b>{car['year'] or '—'}</b>\n"
    )

    if is_admin(update.effective_user.id):
        car_info += f"👤 Клиент: <b>{car['client_name'] or '—'}</b>\n"
        car_info += f"📞 Телефон: <b>{car['client_phone'] or '—'}</b>\n"

    car_info += f"\n{'─' * 30}\n\n"
    car_info += format_services(services)

    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await safe_reply(update, car_info, parse_mode="HTML", reply_markup=kb)
    return ConversationHandler.END

# ===================== АДМИН: ДОБАВЛЕНИЕ АВТО =====================
async def add_car_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    context.user_data.clear()
    await safe_reply(update,
        "Введите VIN-номер автомобиля (17 символов):\n<i>Или нажмите ❌ Отмена</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    return ADDING_CAR_VIN

async def add_car_vin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    vin = re.sub(r'\s+', '', update.message.text.strip().upper())
    if len(vin) != 17:
        await safe_reply(update, "❌ VIN должен содержать ровно 17 символов. Попробуйте снова:")
        return ADDING_CAR_VIN
    context.user_data['vin'] = vin
    await safe_reply(update,
        "Введите госномер автомобиля:\n<i>Форматы: А123БВ177, 01KG123ABC, 12AB123</i>",
        parse_mode="HTML"
    )
    return ADDING_CAR_PLATE

async def add_car_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    plate = update.message.text.strip().upper()
    if not plate or len(plate) < 3:
        await safe_reply(update, "❌ Госномер не может быть пустым. Попробуйте снова:")
        return ADDING_CAR_PLATE
    country = detect_plate_country(plate)
    if country == "Неизвестно":
        country = "РФ"
    context.user_data['plate'] = plate
    context.user_data['plate_country'] = country
    await safe_reply(update, "Введите марку авто (например, Toyota, BMW):")
    return ADDING_CAR_BRAND

async def add_car_brand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    brand = update.message.text.strip()
    if not brand:
        await safe_reply(update, "❌ Марка не может быть пустой. Попробуйте снова:")
        return ADDING_CAR_BRAND
    context.user_data['brand'] = brand
    await safe_reply(update, "Введите модель авто (например, Camry, X5):")
    return ADDING_CAR_MODEL

async def add_car_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    model = update.message.text.strip()
    if not model:
        await safe_reply(update, "❌ Модель не может быть пустой. Попробуйте снова:")
        return ADDING_CAR_MODEL
    context.user_data['model'] = model
    await safe_reply(update, "Введите год выпуска (например, 2023):")
    return ADDING_CAR_YEAR

async def add_car_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    try:
        year = int(update.message.text.strip())
        if year < 1900 or year > 2100:
            await safe_reply(update, "❌ Год должен быть от 1900 до 2100. Попробуйте снова:")
            return ADDING_CAR_YEAR
    except ValueError:
        await safe_reply(update, "❌ Введите число. Попробуйте снова:")
        return ADDING_CAR_YEAR
    context.user_data['year'] = year
    await safe_reply(update, "Введите имя клиента (можно —):")
    return ADDING_CAR_CLIENT_NAME

async def add_car_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    context.user_data['client_name'] = update.message.text.strip() or "—"
    await safe_reply(update, "Введите телефон клиента (можно —):")
    return ADDING_CAR_CLIENT_PHONE

async def add_car_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.clear()
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END

    phone = update.message.text.strip() or "—"

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO cars (vin, plate, plate_country, brand, model, year, client_name, client_phone) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (context.user_data['vin'], context.user_data['plate'], context.user_data['plate_country'],
             context.user_data['brand'], context.user_data['model'], context.user_data['year'],
             context.user_data['client_name'], phone)
        )
        conn.commit()
        await safe_reply(update,
            f"✅ Автомобиль добавлен!\n\n"
            f"🚗 {context.user_data['brand']} {context.user_data['model']} ({context.user_data['year']})\n"
            f"📌 VIN: {context.user_data['vin']}\n"
            f"📋 Госномер: {context.user_data['plate']} ({context.user_data['plate_country']})\n"
            f"👤 Клиент: {context.user_data['client_name']}\n"
            f"📞 Телефон: {phone}",
            reply_markup=admin_kb
        )
    except Exception as e:
        conn.rollback()
        error_msg = str(e)
        if "duplicate" in error_msg.lower() or "уникальным" in error_msg.lower() or "unique" in error_msg.lower():
            await safe_reply(update, "❌ Автомобиль с таким VIN или госномером уже существует.", reply_markup=admin_kb)
        else:
            await safe_reply(update, "❌ Ошибка при сохранении. Попробуйте позже.", reply_markup=admin_kb)
    finally:
        cur.close()
        conn.close()
    
    context.user_data.clear()
    return ConversationHandler.END

# ===================== АДМИН: УДАЛЕНИЕ АВТО =====================
async def delete_car_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cars = get_all_cars()
    if not cars:
        await safe_reply(update, "📭 База автомобилей пуста.", reply_markup=admin_kb)
        return ConversationHandler.END
    text = "🗑 <b>Удаление автомобиля</b>\n\nВыберите ID автомобиля для удаления:\n\n"
    for c in cars:
        plate_str = f"{c['plate']}" if c['plate'] else "без номера"
        text += f"🆔 {c['id']} — {c['brand']} {c['model']} | {plate_str}\n"
    text += "\n<i>ВНИМАНИЕ: Все записи обслуживания тоже удалятся!</i>"
    await safe_reply(update, text, parse_mode="HTML", reply_markup=cancel_kb)
    return DELETE_CAR_ID

async def delete_car_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await safe_reply(update, "❌ Удаление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END

    try:
        car_id = int(update.message.text.strip())
    except ValueError:
        await safe_reply(update, "❌ Отправьте числовой ID автомобиля:")
        return DELETE_CAR_ID

    car = get_car_by_id(car_id)
    if not car:
        await safe_reply(update, "❌ Автомобиль с таким ID не найден.")
        return DELETE_CAR_ID

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM services WHERE car_id = %s", (car_id,))
        cur.execute("DELETE FROM cars WHERE id = %s", (car_id,))
        conn.commit()
        await safe_reply(update,
            f"✅ Автомобиль удалён!\n\n"
            f"🚗 {car['brand']} {car['model']} | {car['plate']}\n"
            f"👤 Клиент: {car['client_name']}",
            reply_markup=admin_kb
        )
    except Exception as e:
        conn.rollback()
        await safe_reply(update, "❌ Ошибка при удалении.", reply_markup=admin_kb)
    finally:
        cur.close()
        conn.close()

    return ConversationHandler.END

# ===================== АДМИН: ВСЕ АВТО =====================
async def list_cars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cars = get_all_cars()
    if not cars:
        await safe_reply(update, "📭 База автомобилей пуста.", reply_markup=admin_kb)
        return
    text = "📋 <b>Последние автомобили в базе:</b>\n\n"
    for c in cars:
        plate_str = f"{c['plate']} ({c['plate_country']})" if c['plate'] else "—"
        text += f"🆔 {c['id']} | {c['brand']} {c['model']} | {plate_str} | {c['client_name']}\n"
    await safe_reply(update, text, parse_mode="HTML", reply_markup=admin_kb)

# ===================== АДМИН: ДОБАВЛЕНИЕ ОБСЛУЖИВАНИЯ =====================
async def add_service_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cars = get_all_cars()
    if not cars:
        await safe_reply(update, "❌ Сначала добавьте автомобиль в базу.", reply_markup=admin_kb)
        return ConversationHandler.END
    text = "Выберите автомобиль (отправьте <b>ID</b>):\n\n"
    for c in cars:
        plate_str = f"{c['plate']}" if c['plate'] else "без номера"
        text += f"🆔 {c['id']} — {c['brand']} {c['model']} | {plate_str}\n"
    await safe_reply(update, text, parse_mode="HTML", reply_markup=cancel_kb)
    return SELECTING_CAR

async def select_car(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    try:
        car_id = int(update.message.text.strip())
    except ValueError:
        await safe_reply(update, "❌ Отправьте числовой ID автомобиля:")
        return SELECTING_CAR

    car = get_car_by_id(car_id)
    if not car:
        await safe_reply(update, "❌ Автомобиль с таким ID не найден.")
        return SELECTING_CAR

    context.user_data['car_id'] = car_id
    context.user_data['car_info'] = f"{car['brand']} {car['model']} ({car['plate']})"
    await safe_reply(update,
        f"🚗 <b>{car['brand']} {car['model']} | {car['plate']}</b>\n\n"
        f"Введите дату обслуживания (ДД.ММ.ГГГГ):",
        parse_mode="HTML"
    )
    return ADDING_SERVICE_DATE

async def add_service_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    raw_date = update.message.text.strip()
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"]:
        try:
            parsed = datetime.strptime(raw_date, fmt)
            context.user_data['service_date'] = parsed.strftime("%Y-%m-%d")
            await safe_reply(update, "Введите пробег (только число, км):")
            return ADDING_SERVICE_MILEAGE
        except ValueError:
            continue
    await safe_reply(update, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:")
    return ADDING_SERVICE_DATE

async def add_service_mileage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END
    try:
        mileage = int(update.message.text.strip().replace(" ", ""))
    except ValueError:
        await safe_reply(update, "❌ Введите число (пробег в км):")
        return ADDING_SERVICE_MILEAGE
    context.user_data['service_mileage'] = mileage
    await safe_reply(update,
        "Теперь введите данные обслуживания в формате <b>Ключ=Значение</b> (каждый с новой строки):\n\n"
        "<code>работы=Замена масла Castrol 5W-30, масляный фильтр, воздушный фильтр\n"
        "мастер=Иванов\n"
        "сумма=12500\n"
        "заметки=Рекомендация: замена ГРМ через 10 000 км</code>\n\n"
        "<b>Доступные ключи:</b>\n"
        "• работы — что сделали (пишите своими словами)\n"
        "• мастер — кто делал\n"
        "• сумма — стоимость\n"
        "• заметки — дополнительная информация\n\n"
        "Можно указать только нужные поля.",
        parse_mode="HTML"
    )
    return ADDING_SERVICE_DETAILS

async def add_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await safe_reply(update, "❌ Добавление отменено.", reply_markup=admin_kb)
        return ConversationHandler.END

    keys_map = {
        'работы': 'work_done',
        'мастер': 'master',
        'сумма': 'total_amount',
        'заметки': 'notes',
    }

    fields = {}
    for line in update.message.text.strip().split('\n'):
        line = line.strip()
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip()
            if key in keys_map:
                key = keys_map[key]
            if key == 'total_amount':
                try:
                    fields[key] = float(value)
                except ValueError:
                    fields[key] = 0
            else:
                fields[key] = value

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO services 
            (car_id, date, mileage, other_work, total_amount, master, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                context.user_data['car_id'], context.user_data['service_date'], context.user_data['service_mileage'],
                fields.get('work_done', ''),
                fields.get('total_amount', 0),
                fields.get('master', ''),
                fields.get('notes', '')
            )
        )
        conn.commit()
        await safe_reply(update,
            f"✅ Запись об обслуживании добавлена!\n\n"
            f"🚗 {context.user_data['car_info']}\n"
            f"📅 Дата: {context.user_data['service_date']}\n"
            f"🔢 Пробег: {context.user_data['service_mileage']:,} км".replace(',', ' '),
            reply_markup=admin_kb
        )
    except Exception as e:
        conn.rollback()
        await safe_reply(update, "❌ Ошибка при сохранении. Попробуйте позже.", reply_markup=admin_kb)
    finally:
        cur.close()
        conn.close()

    return ConversationHandler.END

# ===================== ОБЩИЕ =====================
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update,
        "🔧 <b>Автосервис</b>\n\n"
        "✅ Обслуживание автомобилей с сохранением истории\n"
        "✅ Прозрачность всех работ и материалов\n"
        "✅ Доступ к истории по VIN или госномеру 24/7",
        parse_mode="HTML"
    )

async def contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update,
        "📞 <b>Наши контакты:</b>\n\n"
        "📍 Адрес: укажите здесь\n"
        "📱 Телефон: укажите здесь\n"
        "🕐 Режим работы: укажите здесь",
        parse_mode="HTML"
    )

async def exit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await safe_reply(update, "Вы вышли из админ-панели.", reply_markup=main_kb)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await safe_reply(update, "❌ Действие отменено.", reply_markup=kb)
    return ConversationHandler.END

# ===================== ЗАПУСК =====================
from flask import Flask

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    query_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔍 Запросить историю$"), request_query),
            MessageHandler(filters.Regex("^🔍 Найти авто \\(админ\\)$"), request_query),
        ],
        states={
            WAITING_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_query)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)],
    )
    app.add_handler(query_handler)

    add_car_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить автомобиль$"), add_car_start)],
        states={
            ADDING_CAR_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_vin)],
            ADDING_CAR_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_plate)],
            ADDING_CAR_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_brand)],
            ADDING_CAR_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_model)],
            ADDING_CAR_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_year)],
            ADDING_CAR_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_client_name)],
            ADDING_CAR_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_client_phone)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)],
    )
    app.add_handler(add_car_handler)

    delete_car_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑 Удалить автомобиль$"), delete_car_start)],
        states={
            DELETE_CAR_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_car_confirm)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)],
    )
    app.add_handler(delete_car_handler)

    add_service_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔧 Добавить обслуживание$"), add_service_start)],
        states={
            SELECTING_CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_car)],
            ADDING_SERVICE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_service_date)],
            ADDING_SERVICE_MILEAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_service_mileage)],
            ADDING_SERVICE_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_service_details)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)],
    )
    app.add_handler(add_service_handler)

    app.add_handler(MessageHandler(filters.Regex("^📋 Все автомобили$"), list_cars))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ О сервисе$"), about))
    app.add_handler(MessageHandler(filters.Regex("^📞 Контакты$"), contacts))
    app.add_handler(MessageHandler(filters.Regex("^❌ Выйти из админки$"), exit_admin))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel))

    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()