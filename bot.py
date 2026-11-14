import re
import sqlite3
import threading
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ВСТАВЬТЕ СЮДА ВАШ АКТУАЛЬНЫЙ ТОКЕН ОТ @BotFather
TOKEN = "8972845479:AAH1ui-YcB1-WTaC-EIjMjYZ7fgjCBHNT84" 
ADMIN_IDS = [8621244180, 740869889, 8983954588]
DB_FILE = "autoservice.db"

# ===================== БАЗА ДАННЫХ =====================
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vin TEXT UNIQUE,
            plate TEXT UNIQUE,
            plate_country TEXT DEFAULT 'РФ',
            brand TEXT DEFAULT '',
            model TEXT DEFAULT '',
            year INTEGER DEFAULT 0,
            client_name TEXT DEFAULT '',
            client_phone TEXT DEFAULT '',
            added_date TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            mileage INTEGER NOT NULL,
            other_work TEXT DEFAULT '',
            total_amount REAL DEFAULT 0,
            master TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_info TEXT DEFAULT '',
            work TEXT DEFAULT '',
            remind_at TEXT NOT NULL,
            sent INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()

init_db()

# ===================== КЛАВИАТУРЫ =====================
main_kb = ReplyKeyboardMarkup([
    ["🔍 Запросить историю"],
    ["ℹ️ О сервисе", "📞 Контакты"]
], resize_keyboard=True)

admin_kb = ReplyKeyboardMarkup([
    ["➕ Добавить автомобиль", "🔧 Добавить обслуживание"],
    ["📋 Все автомобили", "🔍 Найти авто"],
    ["🗑 Удалить автомобиль"],
    ["💾 Экспорт базы"],
    ["❌ Выйти из админки"]
], resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)

# ===================== СОСТОЯНИЯ =====================
(QUERY, CAR_VIN, CAR_PLATE, CAR_BRAND, CAR_MODEL, CAR_YEAR,
 CAR_NAME, CAR_PHONE, SVC_SELECT, SVC_DATE, SVC_MILEAGE, SVC_DETAILS,
 DEL_CAR) = range(13)

# ===================== ФУНКЦИИ =====================
def is_admin(uid): return uid in ADMIN_IDS

def plate_country(p):
    p = re.sub(r'\s+', '', p.upper())
    if re.match(r'^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$', p): return "РФ"
    if re.match(r'^\d{2}KG\d{3}[A-Z]{3}$', p): return "Киргизия"
    if re.match(r'^\d{2}[A-Z]{2}\d{3}$', p): return "Армения"
    return "РФ"

def find_car(q):
    q = re.sub(r'\s+', '', q.upper())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cars WHERE UPPER(REPLACE(vin,' ',''))=? OR UPPER(REPLACE(plate,' ',''))=?", (q,q))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def car_services(cid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM services WHERE car_id=? ORDER BY date DESC", (cid,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def all_cars():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cars ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def car_by_id(cid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cars WHERE id=?", (cid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def fmt_services(rows):
    if not rows: return "📭 История обслуживания пуста"
    res = ""
    for s in rows:
        res += f"📅 <b>{s['date']}</b> | Пробег: <b>{s['mileage']:,}</b> км\n".replace(',',' ')
        if s['other_work']: res += f"🔧 <b>Работы:</b> {s['other_work']}\n"
        if s['master']: res += f"👨‍🔧 Мастер: <b>{s['master']}</b>\n"
        if s['total_amount']: res += f"💰 Сумма: <b>{s['total_amount']}</b> ₽\n"
        if s['notes']: res += f"📝 <i>Рекомендации: {s['notes']}</i>\n"
        res += "─" * 25 + "\n"
    return res

def format_remind_time(days: float) -> str:
    if days >= 1:
        if days == int(days): return f"{int(days)} дн."
        return f"{days} дн."
    total_min = int(days * 24 * 60)
    if total_min < 60: return f"{total_min} мин."
    h = total_min // 60
    m = total_min % 60
    if m: return f"{h} ч {m} мин."
    return f"{h} ч."

# ===================== ВОРКЕР НАПОМИНАНИЙ =====================
def reminder_worker():
    import time
    import httpx
    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT * FROM reminders WHERE sent=0 AND remind_at <= ?", (now,))
            rows = cur.fetchall()
            for r in rows:
                r = dict(r)
                text = (
                    f"🔔 <b>Напоминание: позвонить клиенту</b>\n\n"
                    f"🚗 {r['car_info']}\n"
                    f"🔧 Что делали: {r['work'] or '—'}\n\n"
                    f"Позвоните и спросите, всё ли в порядке."
                )
                for admin_id in ADMIN_IDS:
                    try:
                        httpx.post(
                            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                            json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"},
                            timeout=10
                        )
                    except Exception as e:
                        print(f"Reminder send error: {e}")
                cur.execute("UPDATE reminders SET sent=1 WHERE id=?", (r['id'],))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Reminder worker error: {e}")
        time.sleep(30)

# ===================== СТАРТ =====================
async def start(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text("👋 Вас приветствует Автопрестиж, Автосервис и Мойка", reply_markup=kb)

async def admin_cmd(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text("🔐 Админ-панель", reply_markup=admin_kb)

# ===================== МЕНЮ =====================
async def menu_cars(update, context):
    context.user_data.clear()
    cars = all_cars()
    if not cars:
        await update.message.reply_text("📭 База пуста.", reply_markup=admin_kb)
        return
    txt = "📋 <b>Автомобили:</b>\n\n"
    for c in cars:
        txt += f"🆔 {c['id']} | {c['brand']} {c['model']} | {c['plate']}\n"
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=admin_kb)

async def menu_about(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text(
        "🔧 <b>АвтоПрестиж</b>\n\n"
        "✅ Качественный ремонт и обслуживание\n"
        "✅ Оригинальные запчасти\n"
        "✅ Гарантия на все работы\n"
        "✅ Честные цены\n"
        "💦 Профессиональная автомойка",
        parse_mode="HTML",
        reply_markup=kb
    )

async def menu_contacts(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text(
        "📞 <b>Телефон:</b> +7 (922) 679-08-27\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Ленина, д. 10\n"
        "🕐 <b>Режим работы:</b> Вт–Чт, Сб–Вс (Пятница — выходной)\n"
        "💬 <b>WhatsApp:</b> <a href='https://wa.me/79226790827'>Написать в WhatsApp</a>",
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True
    )

async def menu_exit(update, context):
    context.user_data.clear()
    await update.message.reply_text("Вышли из админки.", reply_markup=main_kb)

# ===================== ЭКСПОРТ БАЗЫ =====================
async def export_db(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id): return
    import os
    if os.path.exists(DB_FILE):
        await update.message.reply_document(document=open(DB_FILE, 'rb'), filename="autoservice.db")
    else:
        await update.message.reply_text("❌ Файл базы не найден.")

# ===================== ЗАПРОС ИСТОРИИ =====================
async def query_start(update, context):
    context.user_data.clear()
    await update.message.reply_text("Введите VIN или госномер:", reply_markup=cancel_kb)
    return QUERY

async def query_process(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    car = find_car(update.message.text.strip())
    if not car:
        await update.message.reply_text("❌ Не найдено.", reply_markup=cancel_kb)
        return QUERY
    svc = car_services(car['id'])
    txt = f"🚗 <b>{car['brand']} {car['model']} ({car['year']})</b>\n📌 VIN: {car['vin']}\n📋 {car['plate']} ({car['plate_country']})\n\n{fmt_services(svc)}"
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)
    return ConversationHandler.END

# ===================== ДОБАВЛЕНИЕ АВТО =====================
async def car_start(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("VIN (17 символов):", reply_markup=cancel_kb)
    return CAR_VIN

async def car_vin(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    vin = re.sub(r'\s+', '', update.message.text.strip().upper())
    if len(vin) != 17:
        await update.message.reply_text("❌ Ровно 17 символов:")
        return CAR_VIN
    context.user_data['vin'] = vin
    await update.message.reply_text("Госномер:")
    return CAR_PLATE

async def car_plate(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    p = update.message.text.strip().upper()
    if not p:
        await update.message.reply_text("❌ Введите номер:")
        return CAR_PLATE
    context.user_data['plate'] = p
    context.user_data['pcountry'] = plate_country(p)
    await update.message.reply_text("Марка:")
    return CAR_BRAND

async def car_brand(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    context.user_data['brand'] = update.message.text.strip()
    await update.message.reply_text("Модель:")
    return CAR_MODEL

async def car_model(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    context.user_data['model'] = update.message.text.strip()
    await update.message.reply_text("Год выпуска:")
    return CAR_YEAR

async def car_year(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    try:
        y = int(update.message.text.strip())
        if y < 1900 or y > 2100: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Год от 1900 до 2100:")
        return CAR_YEAR
    context.user_data['year'] = y
    await update.message.reply_text("Имя клиента:")
    return CAR_NAME

async def car_name(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    context.user_data['client_name'] = update.message.text.strip() or "—"
    await update.message.reply_text("Телефон:")
    return CAR_PHONE

async def car_phone(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    phone = update.message.text.strip() or "—"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM cars WHERE vin=? OR plate=?", (context.user_data['vin'], context.user_data['plate']))
        if cur.fetchone():
            await update.message.reply_text("❌ Такой VIN или номер уже существует.", reply_markup=admin_kb)
            context.user_data.clear()
            return ConversationHandler.END

        cur.execute(
            "INSERT INTO cars (vin, plate, plate_country, brand, model, year, client_name, client_phone) VALUES (?,?,?,?,?,?,?,?)",
            (context.user_data['vin'], context.user_data['plate'], context.user_data['pcountry'],
             context.user_data['brand'], context.user_data['model'], context.user_data['year'],
             context.user_data['client_name'], phone)
        )
        conn.commit()
        await update.message.reply_text(
            f"✅ Автомобиль добавлен!\n🚗 {context.user_data['brand']} {context.user_data['model']}\n📌 {context.user_data['vin']}",
            reply_markup=admin_kb
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ Такой VIN или номер уже существует.", reply_markup=admin_kb)
    except Exception as e:
        await update.message.reply_text("❌ Ошибка при сохранении.", reply_markup=admin_kb)
    finally:
        cur.close()
        conn.close()
        context.user_data.clear()
    return ConversationHandler.END

# ===================== ДОБАВЛЕНИЕ ОБСЛУЖИВАНИЯ =====================
async def svc_start(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    cars = all_cars()
    if not cars:
        await update.message.reply_text("❌ Нет автомобилей.", reply_markup=admin_kb)
        return ConversationHandler.END
    txt = "Выберите ID авто:\n\n"
    for c in cars:
        txt += f"🆔 {c['id']} | {c['brand']} {c['model']} | {c['plate']}\n"
    await update.message.reply_text(txt, reply_markup=cancel_kb)
    return SVC_SELECT

async def svc_select(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    try:
        cid = int(update.message.text.strip().replace(" ", ""))
    except ValueError:
        await update.message.reply_text("❌ Введите число (ID авто):")
        return SVC_SELECT
    car = car_by_id(cid)
    if not car:
        await update.message.reply_text("❌ Автомобиль с таким ID не найден.")
        return SVC_SELECT
    context.user_data['car_id'] = cid
    context.user_data['car_info'] = f"{car['brand']} {car['model']} ({car['plate']})"
    await update.message.reply_text(f"🚗 {car['brand']} {car['model']}\n\nДата (ДД.ММ.ГГГГ):")
    return SVC_DATE

async def svc_date(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    raw = update.message.text.strip()
    for fmt in ["%d.%m.%Y", "%Y-%m-%d"]:
        try:
            d = datetime.strptime(raw, fmt)
            context.user_data['svc_date'] = d.strftime("%Y-%m-%d")
            await update.message.reply_text("Пробег (км):")
            return SVC_MILEAGE
        except ValueError:
            continue
    await update.message.reply_text("❌ Формат ДД.ММ.ГГГГ:")
    return SVC_DATE

async def svc_mileage(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    try:
        m = int(update.message.text.strip().replace(" ", ""))
    except ValueError:
        await update.message.reply_text("❌ Введите число (пробег):")
        return SVC_MILEAGE
    context.user_data['svc_mileage'] = m
    await update.message.reply_text(
        "Введите данные:\n\n"
        "работы=Замена масла, фильтры\n"
        "мастер=Иванов\n"
        "сумма=5000\n"
        "рекомендации=Проверить тормоза\n"
        "напомнить=15\n\n"
        "напомнить — через сколько дней напомнить (дробные можно, например 0.001 ≈ 1.5 мин). 0 или не указывать — без напоминания."
    )
    return SVC_DETAILS

async def svc_details(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    fields = {}
    for line in update.message.text.strip().split('\n'):
        if '=' in line:
            k, v = line.split('=', 1)
            k, v = k.strip().lower(), v.strip()
            if k in ('работы',): fields['work'] = v
            elif k == 'мастер': fields['master'] = v
            elif k == 'сумма':
                try: fields['sum'] = float(v)
                except: pass
            elif k == 'рекомендации': fields['notes'] = v
            elif k == 'напомнить':
                try: fields['remind'] = float(v.replace(',', '.'))
                except: pass

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO services (car_id, date, mileage, other_work, total_amount, master, notes) VALUES (?,?,?,?,?,?,?)",
            (context.user_data['car_id'], context.user_data['svc_date'], context.user_data['svc_mileage'],
             fields.get('work',''), fields.get('sum',0), fields.get('master',''), fields.get('notes',''))
        )

        remind_days = fields.get('remind', 0)
        remind_text = ""
        if remind_days and remind_days > 0:
            remind_dt = datetime.now() + timedelta(days=remind_days)
            cur.execute(
                "INSERT INTO reminders (car_info, work, remind_at, sent) VALUES (?,?,?,0)",
                (context.user_data['car_info'], fields.get('work',''),
                 remind_dt.strftime("%Y-%m-%d %H:%M:%S"))
            )
            remind_text = f"\n⏰ Напоминание через {format_remind_time(remind_days)}"

        conn.commit()
        await update.message.reply_text(
            f"✅ Обслуживание добавлено!\n🚗 {context.user_data['car_info']}\n📅 {context.user_data['svc_date']}{remind_text}",
            reply_markup=admin_kb
        )
    except Exception as e:
        conn.rollback()
        await update.message.reply_text("❌ Ошибка при сохранении.", reply_markup=admin_kb)
    finally:
        cur.close()
        conn.close()
        context.user_data.clear()
    return ConversationHandler.END

# ===================== УДАЛЕНИЕ АВТО =====================
async def del_start(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    cars = all_cars()
    if not cars:
        await update.message.reply_text("📭 База пуста.", reply_markup=admin_kb)
        return ConversationHandler.END
    txt = "🗑 ID авто для удаления:\n\n"
    for c in cars:
        txt += f"🆔 {c['id']} | {c['brand']} {c['model']} | {c['plate']}\n"
    await update.message.reply_text(txt, reply_markup=cancel_kb)
    return DEL_CAR

async def del_confirm(update, context):
    if update.message.text == "❌ Отмена": return await cancel(update, context)
    try:
        cid = int(update.message.text.strip().replace(" ", ""))
    except ValueError:
        await update.message.reply_text("❌ Введите число (ID авто):")
        return DEL_CAR
    car = car_by_id(cid)
    if not car:
        await update.message.reply_text("❌ Автомобиль с таким ID не найден.")
        return DEL_CAR

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("DELETE FROM cars WHERE id=?", (cid,))
        conn.commit()
        await update.message.reply_text(f"✅ Удалён: {car['brand']} {car['model']}", reply_markup=admin_kb)
    except Exception as e:
        conn.rollback()
        await update.message.reply_text("❌ Ошибка при удалении.", reply_markup=admin_kb)
    finally:
        cur.close()
        conn.close()
        context.user_data.clear()
    return ConversationHandler.END

# ===================== ОТМЕНА =====================
async def cancel(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text("❌ Отменено.", reply_markup=kb)
    return ConversationHandler.END

# ===================== Flask для порта =====================
from flask import Flask

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "OK"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ===================== ЗАПУСК =====================
def main():
    import os
    import sys

    lock_file = "/tmp/bot.lock"
    if os.path.exists(lock_file):
        print("Бот уже запущен, выхожу...")
        sys.exit(0)
    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=reminder_worker, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    # --- ЗАПРОС ИСТОРИИ ---
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Найти авто$"), query_start),
                      MessageHandler(filters.Regex("^🔍 Запросить историю$"), query_start)],
        states={QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_process)]},
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            MessageHandler(filters.Regex("^➕ Добавить автомобиль$"), car_start),
            MessageHandler(filters.Regex("^🔧 Добавить обслуживание$"), svc_start),
            MessageHandler(filters.Regex("^📋 Все автомобили$"), menu_cars),
            MessageHandler(filters.Regex("^🗑 Удалить автомобиль$"), del_start),
        ],
        allow_reentry=True
    ))

    # --- ДОБАВЛЕНИЕ АВТО ---
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить автомобиль$"), car_start)],
        states={
            CAR_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_vin)],
            CAR_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_plate)],
            CAR_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_brand)],
            CAR_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_model)],
            CAR_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_year)],
            CAR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_name)],
            CAR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, car_phone)]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            MessageHandler(filters.Regex("^🔧 Добавить обслуживание$"), svc_start),
            MessageHandler(filters.Regex("^📋 Все автомобили$"), menu_cars),
        ],
        allow_reentry=True
    ))

    # --- ДОБАВЛЕНИЕ ОБСЛУЖИВАНИЯ ---
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔧 Добавить обслуживание$"), svc_start)],
        states={
            SVC_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_select)],
            SVC_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_date)],
            SVC_MILEAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_mileage)],
            SVC_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_details)]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            MessageHandler(filters.Regex("^➕ Добавить автомобиль$"), car_start),
            MessageHandler(filters.Regex("^📋 Все автомобили$"), menu_cars),
        ],
        allow_reentry=True
    ))

    # --- УДАЛЕНИЕ АВТО ---
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑 Удалить автомобиль$"), del_start)],
        states={DEL_CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_confirm)]},
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            MessageHandler(filters.Regex("^➕ Добавить автомобиль$"), car_start),
            MessageHandler(filters.Regex("^🔧 Добавить обслуживание$"), svc_start),
            MessageHandler(filters.Regex("^📋 Все автомобили$"), menu_cars),
        ],
        allow_reentry=True
    ))

    app.add_handler(MessageHandler(filters.Regex("^📋 Все автомобили$"), menu_cars))
    app.add_handler(MessageHandler(filters.Regex("^💾 Экспорт базы$"), export_db))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ О сервисе$"), menu_about))
    app.add_handler(MessageHandler(filters.Regex("^📞 Контакты$"), menu_contacts))
    app.add_handler(MessageHandler(filters.Regex("^❌ Выйти из админки$"), menu_exit))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel))

    print("Бот запущен!")
    app.run_polling(drop_pending_updates=True)
    os.remove(lock_file)

if __name__ == "__main__":
    main()