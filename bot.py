import asyncio
import re
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, ReplyKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardRemove)

# ===================== НАСТРОЙКИ =====================
TOKEN = "8972845479:AAFkpr9Bc0K2UBA8x3hZmobPlKLUK-4PKtA"
ADMIN_IDS = [8621244180,740869889,8983954588]

# ===================== БАЗА ДАННЫХ =====================
def init_db():
    conn = sqlite3.connect("autoservice.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vin TEXT UNIQUE,
            plate TEXT UNIQUE,
            plate_country TEXT,
            brand TEXT DEFAULT '',
            model TEXT DEFAULT '',
            year INTEGER DEFAULT 0,
            client_name TEXT DEFAULT '',
            client_phone TEXT DEFAULT '',
            added_date TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            mileage INTEGER NOT NULL,
            oil_type TEXT DEFAULT '',
            oil_volume TEXT DEFAULT '',
            oil_filter TEXT DEFAULT 'Да',
            air_filter TEXT DEFAULT 'Да',
            cabin_filter TEXT DEFAULT 'Да',
            fuel_filter TEXT DEFAULT 'Нет',
            brake_pads_front TEXT DEFAULT '',
            brake_pads_rear TEXT DEFAULT '',
            brake_discs_front TEXT DEFAULT '',
            brake_discs_rear TEXT DEFAULT '',
            brake_fluid TEXT DEFAULT '',
            coolant TEXT DEFAULT '',
            transmission_oil TEXT DEFAULT '',
            spark_plugs TEXT DEFAULT '',
            timing_belt TEXT DEFAULT '',
            drive_belt TEXT DEFAULT '',
            battery TEXT DEFAULT '',
            suspension_work TEXT DEFAULT '',
            steering_work TEXT DEFAULT '',
            exhaust_work TEXT DEFAULT '',
            diagnosis TEXT DEFAULT '',
            other_work TEXT DEFAULT '',
            total_amount REAL DEFAULT 0,
            master TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (car_id) REFERENCES cars(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ===================== СОСТОЯНИЯ FSM =====================
class ClientStates(StatesGroup):
    waiting_query = State()

class AdminStates(StatesGroup):
    choosing_action = State()
    adding_car_vin = State()
    adding_car_plate = State()
    adding_car_brand = State()
    adding_car_model = State()
    adding_car_year = State()
    adding_car_client_name = State()
    adding_car_client_phone = State()
    selecting_car_for_service = State()
    adding_service_date = State()
    adding_service_mileage = State()
    adding_service_details = State()

# ===================== КЛАВИАТУРЫ =====================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Запросить историю")],
        [KeyboardButton(text="ℹ️ О сервисе"), KeyboardButton(text="📞 Контакты")]
    ],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить автомобиль")],
        [KeyboardButton(text="🔧 Добавить обслуживание")],
        [KeyboardButton(text="📋 Все автомобили")],
        [KeyboardButton(text="🔍 Найти авто (админ)")],
        [KeyboardButton(text="❌ Выйти из админки")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

# ===================== БОТ И РОУТЕР =====================
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

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

def format_services(services: list) -> str:
    if not services:
        return "📭 История обслуживания пуста"

    result = ""
    for s in services:
        parts = []
        parts.append(f"📅 <b>{s['date']}</b> | Пробег: <b>{s['mileage']:,} км</b>".replace(',', ' '))

        if s['oil_type']:
            parts.append(f"🛢 Масло: <b>{s['oil_type']}</b> ({s['oil_volume']})")

        works = []
        if s['oil_filter'] == 'Да': works.append("масляный фильтр")
        if s['air_filter'] == 'Да': works.append("воздушный фильтр")
        if s['cabin_filter'] == 'Да': works.append("салонный фильтр")
        if s['fuel_filter'] == 'Да': works.append("топливный фильтр")
        if s['brake_pads_front']: works.append(f"передние колодки: {s['brake_pads_front']}")
        if s['brake_pads_rear']: works.append(f"задние колодки: {s['brake_pads_rear']}")
        if s['brake_discs_front']: works.append(f"передние диски: {s['brake_discs_front']}")
        if s['brake_discs_rear']: works.append(f"задние диски: {s['brake_discs_rear']}")
        if s['brake_fluid']: works.append(f"тормозная жидкость: {s['brake_fluid']}")
        if s['coolant']: works.append(f"антифриз: {s['coolant']}")
        if s['transmission_oil']: works.append(f"масло КПП: {s['transmission_oil']}")
        if s['spark_plugs']: works.append(f"свечи: {s['spark_plugs']}")
        if s['timing_belt']: works.append(f"ремень ГРМ: {s['timing_belt']}")
        if s['drive_belt']: works.append(f"приводной ремень: {s['drive_belt']}")
        if s['battery']: works.append(f"АКБ: {s['battery']}")
        if s['suspension_work']: works.append(f"подвеска: {s['suspension_work']}")
        if s['steering_work']: works.append(f"рулевое: {s['steering_work']}")
        if s['exhaust_work']: works.append(f"выхлоп: {s['exhaust_work']}")
        if s['diagnosis']: works.append(f"диагностика: {s['diagnosis']}")
        if s['other_work']: works.append(f"прочее: {s['other_work']}")

        if works:
            parts.append(f"🔧 <b>Работы:</b> {', '.join(works)}")

        if s['master']:
            parts.append(f"👨‍🔧 Мастер: <b>{s['master']}</b>")
        if s['total_amount']:
            parts.append(f"💰 Сумма: <b>{s['total_amount']} ₽</b>")
        if s['notes']:
            parts.append(f"📝 <i>{s['notes']}</i>")

        result += "\n".join(parts) + "\n" + "─" * 25 + "\n"

    return result

def search_car(query: str) -> dict | None:
    conn = sqlite3.connect("autoservice.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    query_clean = re.sub(r'\s+', '', query.upper())
    cur.execute("SELECT * FROM cars WHERE UPPER(REPLACE(vin, ' ', '')) = ? OR UPPER(REPLACE(plate, ' ', '')) = ?",
                (query_clean, query_clean))
    car = cur.fetchone()
    conn.close()
    return dict(car) if car else None

def get_services(car_id: int) -> list:
    conn = sqlite3.connect("autoservice.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM services WHERE car_id = ? ORDER BY date DESC", (car_id,))
    services = [dict(row) for row in cur.fetchall()]
    conn.close()
    return services

def get_all_cars() -> list:
    conn = sqlite3.connect("autoservice.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM cars ORDER BY id DESC LIMIT 20")
    cars = [dict(row) for row in cur.fetchall()]
    conn.close()
    return cars

# ===================== КОМАНДЫ =====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        await message.answer(
            "👋 Добро пожаловать, администратор!\n\n"
            "Выберите действие в меню:",
            reply_markup=admin_kb
        )
    else:
        await message.answer(
            "👋 Добро пожаловать в автосервис!\n\n"
            "Нажмите кнопку ниже, чтобы запросить историю обслуживания вашего автомобиля.",
            reply_markup=main_kb
        )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    await message.answer("🔐 Админ-панель активна.\nВыберите действие:", reply_markup=admin_kb)

# ===================== ЗАПРОС ИСТОРИИ =====================
@router.message(F.text == "🔍 Запросить историю")
@router.message(F.text == "🔍 Найти авто (админ)")
async def request_query(message: Message, state: FSMContext):
    await state.set_state(ClientStates.waiting_query)
    await message.answer(
        "Введите VIN-номер (17 символов) или госномер автомобиля:\n\n"
        "<i>Примеры:\n"
        "• РФ: А123БВ177 или А123БВ 177\n"
        "• Киргизия: 01KG123ABC\n"
        "• Армения: 12AB123</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(ClientStates.waiting_query)
async def process_query(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        kb = admin_kb if is_admin(message.from_user.id) else main_kb
        await message.answer("❌ Запрос отменён.", reply_markup=kb)
        return

    query = message.text.strip()
    car = search_car(query)

    if not car:
        await message.answer(
            "❌ Автомобиль не найден.\n"
            "Проверьте VIN или госномер и попробуйте снова.\n\n"
            "Если автомобиль обслуживался у нас, обратитесь к администратору.",
            reply_markup=cancel_kb
        )
        return

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

    if is_admin(message.from_user.id):
        car_info += f"👤 Клиент: <b>{car['client_name'] or '—'}</b>\n"
        car_info += f"📞 Телефон: <b>{car['client_phone'] or '—'}</b>\n"

    car_info += f"\n{'─' * 30}\n\n"
    car_info += format_services(services)

    kb = admin_kb if is_admin(message.from_user.id) else main_kb
    if len(car_info) > 4000:
        parts = [car_info[i:i+4000] for i in range(0, len(car_info), 4000)]
        for i, part in enumerate(parts):
            if i == 0:
                await message.answer(part, parse_mode="HTML")
            else:
                await message.answer(part, parse_mode="HTML")
        await message.answer("✅ Это вся история обслуживания.", reply_markup=kb)
    else:
        await message.answer(car_info, parse_mode="HTML", reply_markup=kb)

    await state.clear()

# ===================== АДМИН: ДОБАВЛЕНИЕ АВТО =====================
@router.message(F.text == "➕ Добавить автомобиль")
async def add_car_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.adding_car_vin)
    await message.answer(
        "Введите VIN-номер автомобиля (17 символов):\n<i>Или нажмите ❌ Отмена</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(AdminStates.adding_car_vin)
async def add_car_vin(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    vin = re.sub(r'\s+', '', message.text.strip().upper())
    if len(vin) != 17:
        await message.answer("❌ VIN должен содержать ровно 17 символов. Попробуйте снова:")
        return
    await state.update_data(vin=vin)
    await state.set_state(AdminStates.adding_car_plate)
    await message.answer(
        "Введите госномер автомобиля:\n<i>Форматы: А123БВ177, 01KG123ABC, 12AB123</i>",
        parse_mode="HTML"
    )

@router.message(AdminStates.adding_car_plate)
async def add_car_plate(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    plate = message.text.strip().upper()
    country = detect_plate_country(plate)
    if country == "Неизвестно":
        country = "РФ"
    await state.update_data(plate=plate, plate_country=country)
    await state.set_state(AdminStates.adding_car_brand)
    await message.answer("Введите марку авто (например, Toyota, BMW):")

@router.message(AdminStates.adding_car_brand)
async def add_car_brand(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    await state.update_data(brand=message.text.strip())
    await state.set_state(AdminStates.adding_car_model)
    await message.answer("Введите модель авто (например, Camry, X5):")

@router.message(AdminStates.adding_car_model)
async def add_car_model(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    await state.update_data(model=message.text.strip())
    await state.set_state(AdminStates.adding_car_year)
    await message.answer("Введите год выпуска (например, 2023):")

@router.message(AdminStates.adding_car_year)
async def add_car_year(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    try:
        year = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число. Попробуйте снова:")
        return
    await state.update_data(year=year)
    await state.set_state(AdminStates.adding_car_client_name)
    await message.answer("Введите имя клиента (можно оставить прочерк —):")

@router.message(AdminStates.adding_car_client_name)
async def add_car_client_name(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    await state.update_data(client_name=message.text.strip())
    await state.set_state(AdminStates.adding_car_client_phone)
    await message.answer("Введите телефон клиента (можно оставить прочерк —):")

@router.message(AdminStates.adding_car_client_phone)
async def add_car_client_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    data = await state.get_data()
    conn = sqlite3.connect("autoservice.db")
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO cars (vin, plate, plate_country, brand, model, year, client_name, client_phone) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (data['vin'], data['plate'], data['plate_country'], data['brand'], data['model'],
             data['year'], data['client_name'], message.text.strip())
        )
        conn.commit()
        await message.answer(
            f"✅ Автомобиль добавлен!\n\n"
            f"🚗 {data['brand']} {data['model']} ({data['year']})\n"
            f"📌 VIN: <code>{data['vin']}</code>\n"
            f"📋 Госномер: <b>{data['plate']}</b> ({data['plate_country']})\n"
            f"👤 Клиент: <b>{data['client_name']}</b>\n"
            f"📞 Телефон: <b>{message.text.strip()}</b>",
            reply_markup=admin_kb,
            parse_mode="HTML"
        )
    except sqlite3.IntegrityError:
        await message.answer("❌ Автомобиль с таким VIN или госномером уже существует.", reply_markup=admin_kb)
    finally:
        conn.close()
    await state.clear()

# ===================== АДМИН: ВСЕ АВТО =====================
@router.message(F.text == "📋 Все автомобили")
async def list_cars(message: Message):
    if not is_admin(message.from_user.id):
        return
    cars = get_all_cars()
    if not cars:
        await message.answer("📭 База автомобилей пуста.", reply_markup=admin_kb)
        return
    text = "📋 <b>Последние автомобили в базе:</b>\n\n"
    for c in cars:
        plate_str = f"{c['plate']} ({c['plate_country']})" if c['plate'] else "—"
        text += f"🆔 {c['id']} | {c['brand']} {c['model']} | {plate_str} | {c['client_name']}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=admin_kb)

# ===================== АДМИН: ДОБАВЛЕНИЕ ОБСЛУЖИВАНИЯ =====================
@router.message(F.text == "🔧 Добавить обслуживание")
async def add_service_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    cars = get_all_cars()
    if not cars:
        await message.answer("❌ Сначала добавьте автомобиль в базу.", reply_markup=admin_kb)
        return
    text = "Выберите автомобиль (отправьте <b>ID</b>):\n\n"
    for c in cars:
        plate_str = f"{c['plate']}" if c['plate'] else "без номера"
        text += f"🆔 {c['id']} — {c['brand']} {c['model']} | {plate_str}\n"
    await state.set_state(AdminStates.selecting_car_for_service)
    await message.answer(text, parse_mode="HTML", reply_markup=cancel_kb)

@router.message(AdminStates.selecting_car_for_service)
async def select_car_for_service(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    try:
        car_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Отправьте числовой ID автомобиля:")
        return
    conn = sqlite3.connect("autoservice.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM cars WHERE id = ?", (car_id,))
    car = cur.fetchone()
    conn.close()
    if not car:
        await message.answer("❌ Автомобиль с таким ID не найден.")
        return
    car = dict(car)
    await state.update_data(car_id=car_id, car_info=f"{car['brand']} {car['model']} ({car['plate']})")
    await state.set_state(AdminStates.adding_service_date)
    await message.answer(
        f"🚗 <b>{car['brand']} {car['model']} | {car['plate']}</b>\n\n"
        f"Введите дату обслуживания (ДД.ММ.ГГГГ):",
        parse_mode="HTML"
    )

@router.message(AdminStates.adding_service_date)
async def add_service_date(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    raw_date = message.text.strip()
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"]:
        try:
            parsed = datetime.strptime(raw_date, fmt)
            formatted_date = parsed.strftime("%Y-%m-%d")
            await state.update_data(service_date=formatted_date)
            await state.set_state(AdminStates.adding_service_mileage)
            await message.answer("Введите пробег (только число, км):")
            return
        except ValueError:
            continue
    await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:")

@router.message(AdminStates.adding_service_mileage)
async def add_service_mileage(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return
    try:
        mileage = int(message.text.strip().replace(" ", ""))
    except ValueError:
        await message.answer("❌ Введите число (пробег в км):")
        return
    await state.update_data(service_mileage=mileage)
    await state.set_state(AdminStates.adding_service_details)
    await message.answer(
        "Теперь введите данные обслуживания <b>одним сообщением</b> "
        "в формате Ключ=Значение (каждый с новой строки):\n\n"
        "<code>oil_type=Castrol 5W-30\n"
        "oil_volume=4.2л\n"
        "oil_filter=Да\n"
        "air_filter=Да\n"
        "cabin_filter=Да\n"
        "master=Иванов\n"
        "total_amount=12500\n"
        "notes=Рекомендация: замена ГРМ через 10 000 км</code>\n\n"
        "Можно указать только нужные поля.",
        parse_mode="HTML"
    )

@router.message(AdminStates.adding_service_details)
async def add_service_details(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Добавление отменено.", reply_markup=admin_kb)
        return

    data = await state.get_data()
    fields = {}
    allowed_keys = [
        'oil_type', 'oil_volume', 'oil_filter', 'air_filter', 'cabin_filter',
        'fuel_filter', 'brake_pads_front', 'brake_pads_rear', 'brake_discs_front',
        'brake_discs_rear', 'brake_fluid', 'coolant', 'transmission_oil',
        'spark_plugs', 'timing_belt', 'drive_belt', 'battery', 'suspension_work',
        'steering_work', 'exhaust_work', 'diagnosis', 'other_work',
        'total_amount', 'master', 'notes'
    ]

    for line in message.text.strip().split('\n'):
        line = line.strip()
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip()
            if key in allowed_keys:
                if key == 'total_amount':
                    try:
                        fields[key] = float(value)
                    except ValueError:
                        fields[key] = 0
                else:
                    fields[key] = value

    conn = sqlite3.connect("autoservice.db")
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO services 
        (car_id, date, mileage, oil_type, oil_volume, oil_filter, air_filter, cabin_filter,
        fuel_filter, brake_pads_front, brake_pads_rear, brake_discs_front, brake_discs_rear,
        brake_fluid, coolant, transmission_oil, spark_plugs, timing_belt, drive_belt,
        battery, suspension_work, steering_work, exhaust_work, diagnosis, other_work,
        total_amount, master, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data['car_id'], data['service_date'], data['service_mileage'],
            fields.get('oil_type', ''), fields.get('oil_volume', ''),
            fields.get('oil_filter', 'Да'), fields.get('air_filter', 'Да'),
            fields.get('cabin_filter', 'Да'), fields.get('fuel_filter', 'Нет'),
            fields.get('brake_pads_front', ''), fields.get('brake_pads_rear', ''),
            fields.get('brake_discs_front', ''), fields.get('brake_discs_rear', ''),
            fields.get('brake_fluid', ''), fields.get('coolant', ''),
            fields.get('transmission_oil', ''), fields.get('spark_plugs', ''),
            fields.get('timing_belt', ''), fields.get('drive_belt', ''),
            fields.get('battery', ''), fields.get('suspension_work', ''),
            fields.get('steering_work', ''), fields.get('exhaust_work', ''),
            fields.get('diagnosis', ''), fields.get('other_work', ''),
            fields.get('total_amount', 0), fields.get('master', ''),
            fields.get('notes', '')
        )
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ Запись об обслуживании добавлена!\n\n"
        f"🚗 {data['car_info']}\n"
        f"📅 Дата: <b>{data['service_date']}</b>\n"
        f"🔢 Пробег: <b>{data['service_mileage']:,} км</b>".replace(',', ' '),
        reply_markup=admin_kb,
        parse_mode="HTML"
    )
    await state.clear()

# ===================== ОБЩИЕ =====================
@router.message(F.text == "ℹ️ О сервисе")
async def about_service(message: Message):
    await message.answer(
        "🔧 <b>Автосервис</b>\n\n"
        "✅ Обслуживание автомобилей с сохранением истории\n"
        "✅ Прозрачность всех работ и материалов\n"
        "✅ Доступ к истории по VIN или госномеру 24/7",
        parse_mode="HTML"
    )

@router.message(F.text == "📞 Контакты")
async def contacts(message: Message):
    await message.answer(
        "📞 <b>Наши контакты:</b>\n\n"
        "📍 Адрес: укажите здесь\n"
        "📱 Телефон: укажите здесь\n"
        "🕐 Режим работы: укажите здесь",
        parse_mode="HTML"
    )

@router.message(F.text == "❌ Выйти из админки")
async def exit_admin(message: Message):
    if is_admin(message.from_user.id):
        await message.answer("Вы вышли из админ-панели.", reply_markup=main_kb)

@router.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    kb = admin_kb if is_admin(message.from_user.id) else main_kb
    await message.answer("❌ Действие отменено.", reply_markup=kb)

# ===================== ЗАПУСК =====================
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())