import re
import threading
import httpx
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ===================== НАСТРОЙКИ =====================
TOKEN = "8972845479:AAFkpr9Bc0K2UBA8x3hZmobPlKLUK-4PKtA"
ADMIN_IDS = [8621244180,740869889,8983954588]
SUPABASE_URL = "https://vguziihdwdpkxngpwqrs.supabase.co"
SUPABASE_KEY = "sb_publishable_liWQgdvZTDf5pwGcfK6EGQ_qJhAcSXt"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ===================== БАЗА ДАННЫХ =====================
def db_get(path, params=None):
    try:
        r = httpx.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, params=params, timeout=10)
        return r.json() if r.status_code == 200 else []
    except:
        return []

def db_post(path, data):
    try:
        r = httpx.post(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, json=data, timeout=10)
        return r
    except:
        return None

def db_delete(path, params):
    try:
        r = httpx.delete(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, params=params, timeout=10)
        return r
    except:
        return None

# ===================== КЛАВИАТУРЫ =====================
main_kb = ReplyKeyboardMarkup([
    ["🔍 Запросить историю"],
    ["ℹ️ О сервисе", "📞 Контакты"]
], resize_keyboard=True)

admin_kb = ReplyKeyboardMarkup([
    ["➕ Добавить автомобиль", "🔧 Добавить обслуживание"],
    ["📋 Все автомобили", "🔍 Найти авто"],
    ["🗑 Удалить автомобиль"],
    ["❌ Выйти из админки"]
], resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)

# ===================== СОСТОЯНИЯ =====================
(QUERY, CAR_VIN, CAR_PLATE, CAR_BRAND, CAR_MODEL, CAR_YEAR,
 CAR_NAME, CAR_PHONE, SVC_SELECT, SVC_DATE, SVC_MILEAGE, SVC_DETAILS,
 DEL_CAR) = range(13)

# ===================== ФУНКЦИИ =====================
def is_admin(uid):
    return uid in ADMIN_IDS

def plate_country(p):
    p = re.sub(r'\s+', '', p.upper())
    if re.match(r'^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$', p):
        return "РФ"
    if re.match(r'^\d{2}KG\d{3}[A-Z]{3}$', p):
        return "Киргизия"
    if re.match(r'^\d{2}[A-Z]{2}\d{3}$', p):
        return "Армения"
    return "РФ"

def find_car(q):
    q = re.sub(r'\s+', '', q.upper())
    cars = db_get("cars", {"or": f"(vin.eq.{q},plate.eq.{q})"})
    return cars[0] if cars else None

def car_services(cid):
    return db_get("services", {"car_id": f"eq.{cid}", "order": "date.desc"})

def all_cars():
    return db_get("cars", {"order": "id.desc", "limit": "20"})

def car_by_id(cid):
    cars = db_get("cars", {"id": f"eq.{cid}"})
    return cars[0] if cars else None

def fmt_services(rows):
    if not rows:
        return "📭 История обслуживания пуста"
    res = ""
    for s in rows:
        res += f"📅 <b>{s['date']}</b> | Пробег: <b>{s['mileage']:,}</b> км\n".replace(',', ' ')
        if s.get('other_work'):
            res += f"🔧 <b>Работы:</b> {s['other_work']}\n"
        if s.get('master'):
            res += f"👨‍🔧 Мастер: <b>{s['master']}</b>\n"
        if s.get('total_amount'):
            res += f"💰 Сумма: <b>{s['total_amount']}</b> ₽\n"
        if s.get('notes'):
            res += f"📝 <i>Рекомендации: {s['notes']}</i>\n"
        res += "─" * 25 + "\n"
    return res

# ===================== СТАРТ =====================
async def start(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text("👋 Добро пожаловать!", reply_markup=kb)

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
    await update.message.reply_text("🔧 <b>Автосервис</b>\n\n✅ История обслуживания 24/7", parse_mode="HTML", reply_markup=kb)

async def menu_contacts(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text("📞 +7 (999) 123-45-67\n📍 ул. Автомобильная, 1", reply_markup=kb)

async def menu_exit(update, context):
    context.user_data.clear()
    await update.message.reply_text("Вышли из админки.", reply_markup=main_kb)

# ===================== ЗАПРОС ИСТОРИИ =====================
async def query_start(update, context):
    context.user_data.clear()
    await update.message.reply_text("Введите VIN или госномер:", reply_markup=cancel_kb)
    return QUERY

async def query_process(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
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
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text("VIN (17 символов):", reply_markup=cancel_kb)
    return CAR_VIN

async def car_vin(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    vin = re.sub(r'\s+', '', update.message.text.strip().upper())
    if len(vin) != 17:
        await update.message.reply_text("❌ Ровно 17 символов:")
        return CAR_VIN
    context.user_data['vin'] = vin
    await update.message.reply_text("Госномер:")
    return CAR_PLATE

async def car_plate(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    p = update.message.text.strip().upper()
    if not p:
        await update.message.reply_text("❌ Введите номер:")
        return CAR_PLATE
    context.user_data['plate'] = p
    context.user_data['pcountry'] = plate_country(p)
    await update.message.reply_text("Марка:")
    return CAR_BRAND

async def car_brand(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    context.user_data['brand'] = update.message.text.strip()
    await update.message.reply_text("Модель:")
    return CAR_MODEL

async def car_model(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    context.user_data['model'] = update.message.text.strip()
    await update.message.reply_text("Год выпуска:")
    return CAR_YEAR

async def car_year(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    try:
        y = int(update.message.text.strip())
        if y < 1900 or y > 2100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Год от 1900 до 2100:")
        return CAR_YEAR
    context.user_data['year'] = y
    await update.message.reply_text("Имя клиента:")
    return CAR_NAME

async def car_name(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    context.user_data['client_name'] = update.message.text.strip() or "—"
    await update.message.reply_text("Телефон:")
    return CAR_PHONE

async def car_phone(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    phone = update.message.text.strip() or "—"

    # Проверяем дубликат
    existing = db_get("cars", {"or": f"(vin.eq.{context.user_data['vin']},plate.eq.{context.user_data['plate']})"})
    if existing:
        await update.message.reply_text("❌ Такой VIN или номер уже существует.", reply_markup=admin_kb)
        context.user_data.clear()
        return ConversationHandler.END

    data = {
        "vin": context.user_data['vin'],
        "plate": context.user_data['plate'],
        "plate_country": context.user_data['pcountry'],
        "brand": context.user_data['brand'],
        "model": context.user_data['model'],
        "year": context.user_data['year'],
        "client_name": context.user_data['client_name'],
        "client_phone": phone
    }
    r = db_post("cars", data)

    if r is not None and r.status_code == 201:
        await update.message.reply_text(
            f"✅ Автомобиль добавлен!\n🚗 {context.user_data['brand']} {context.user_data['model']}\n📌 {context.user_data['vin']}",
            reply_markup=admin_kb
        )
    else:
        await update.message.reply_text("❌ Ошибка при сохранении. Попробуйте позже.", reply_markup=admin_kb)

    context.user_data.clear()
    return ConversationHandler.END

# ===================== ДОБАВЛЕНИЕ ОБСЛУЖИВАНИЯ =====================
async def svc_start(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
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
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    try:
        cid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число:")
        return SVC_SELECT
    car = car_by_id(cid)
    if not car:
        await update.message.reply_text("❌ Не найден.")
        return SVC_SELECT
    context.user_data['car_id'] = cid
    context.user_data['car_info'] = f"{car['brand']} {car['model']} ({car['plate']})"
    await update.message.reply_text(f"🚗 {car['brand']} {car['model']}\n\nДата (ДД.ММ.ГГГГ):")
    return SVC_DATE

async def svc_date(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
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
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    try:
        m = int(update.message.text.strip().replace(" ", ""))
    except ValueError:
        await update.message.reply_text("❌ Введите число:")
        return SVC_MILEAGE
    context.user_data['svc_mileage'] = m
    await update.message.reply_text(
        "Введите данные:\n\n"
        "работы=Замена масла, фильтры\n"
        "мастер=Иванов\n"
        "сумма=5000\n"
        "рекомендации=Проверить тормоза"
    )
    return SVC_DETAILS

async def svc_details(update, context):
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    fields = {}
    for line in update.message.text.strip().split('\n'):
        if '=' in line:
            k, v = line.split('=', 1)
            k, v = k.strip().lower(), v.strip()
            if k in ('работы',):
                fields['work'] = v
            elif k == 'мастер':
                fields['master'] = v
            elif k == 'сумма':
                try:
                    fields['sum'] = float(v)
                except:
                    pass
            elif k == 'рекомендации':
                fields['notes'] = v

    data = {
        "car_id": context.user_data['car_id'],
        "date": context.user_data['svc_date'],
        "mileage": context.user_data['svc_mileage'],
        "other_work": fields.get('work', ''),
        "total_amount": fields.get('sum', 0),
        "master": fields.get('master', ''),
        "notes": fields.get('notes', '')
    }
    db_post("services", data)

    await update.message.reply_text(
        f"✅ Обслуживание добавлено!\n🚗 {context.user_data['car_info']}\n📅 {context.user_data['svc_date']}",
        reply_markup=admin_kb
    )
    context.user_data.clear()
    return ConversationHandler.END

# ===================== УДАЛЕНИЕ АВТО =====================
async def del_start(update, context):
    context.user_data.clear()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
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
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
    try:
        cid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число:")
        return DEL_CAR
    car = car_by_id(cid)
    if not car:
        await update.message.reply_text("❌ Не найден.")
        return DEL_CAR

    db_delete("services", {"car_id": f"eq.{cid}"})
    db_delete("cars", {"id": f"eq.{cid}"})

    await update.message.reply_text(f"✅ Удалён: {car['brand']} {car['model']}", reply_markup=admin_kb)
    context.user_data.clear()
    return ConversationHandler.END

# ===================== ОТМЕНА =====================
async def cancel(update, context):
    context.user_data.clear()
    kb = admin_kb if is_admin(update.effective_user.id) else main_kb
    await update.message.reply_text("❌ Отменено.", reply_markup=kb)
    return ConversationHandler.END

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

    try:
        app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Найти авто$"), query_start),
                      MessageHandler(filters.Regex("^🔍 Запросить историю$"), query_start)],
        states={QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_process)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)]
    ))

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
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔧 Добавить обслуживание$"), svc_start)],
        states={
            SVC_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_select)],
            SVC_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_date)],
            SVC_MILEAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_mileage)],
            SVC_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_details)]
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑 Удалить автомобиль$"), del_start)],
        states={DEL_CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_confirm)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), cancel)]
    ))

    app.add_handler(MessageHandler(filters.Regex("^📋 Все автомобили$"), menu_cars))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ О сервисе$"), menu_about))
    app.add_handler(MessageHandler(filters.Regex("^📞 Контакты$"), menu_contacts))
    app.add_handler(MessageHandler(filters.Regex("^❌ Выйти из админки$"), menu_exit))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel))

    print("Бот запущен!")
        app.run_polling(drop_pending_updates=True)

    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)

if __name__ == "__main__":
    main()