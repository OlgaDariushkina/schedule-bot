!pip install python-telegram-bot pandas openpyxl nest_asyncio workalendar transformers torch sentencepiece protobuf accelerate
import logging
import pandas as pd
import os
import calendar
import nest_asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from workalendar.europe import Russia

nest_asyncio.apply()

# ===== КОНФИГУРАЦИЯ =====
# ВНИМАНИЕ: ЗАМЕНИ ТОКЕН НА СВОЙ!
BOT_TOKEN = "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН"  # Получи у @BotFather в Telegram
EXCEL_FILE = "data/schedule.xlsx"  # Теперь файл в папке data

# Создаем папку data если её нет
os.makedirs("data", exist_ok=True)

TIME_SLOTS = [
    "10:15-11:45", "12:00-13:30", "14:15-15:45", "16:00-17:30", 
    "17:40-19:05", "19:15-20:40", "20:45-22:10"
]

DISCIPLINES = [
    "Обработка естественного языка",
    "Инструменты бизнес-аналитики", 
    "Спортивный анализ",
    "Проектный практикум 3",
    "Производственная практика, НИР",
    "Практика: вебинар",
    "Практика: встреча с ментором"
]

# ===== ПРАЗДНИЧНЫЕ ДНИ РОССИИ 2025-2026 =====
MANUAL_HOLIDAYS = [
    "2025-11-03", "2025-11-04",
    "2025-12-31",
    "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05",
    "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10", "2026-01-11",
    "2026-02-21", "2026-02-22", "2026-02-23",
    "2026-03-07", "2026-03-08", "2026-03-09",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-09", "2026-05-10", "2026-05-11",
    "2026-06-12", "2026-06-13", "2026-06-14",
    "2026-11-04",
    "2026-12-31",
]

def is_holiday(date_str):
    """Проверяет, является ли дата праздником"""
    if date_str in MANUAL_HOLIDAYS:
        return True
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        cal = Russia()
        return cal.is_holiday(date_obj)
    except:
        return False

# ===== РАБОЧАЯ AI МОДЕЛЬ =====
print("🔄 Загружаю AI модель...")

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
    
    model_name = "cointegrated/rubert-tiny2-cedr-emotion-detection"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    
    ai_classifier = pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer
    )
    
    print("✅ AI модель загружена и готова к работе!")
    
except Exception as e:
    print(f"❌ Ошибка загрузки AI модели: {e}")
    ai_classifier = None

def smart_ai_analysis(user_message):
    """УМНЫЙ анализ запроса с помощью AI"""
    if ai_classifier is None:
        return extract_keywords_advanced(user_message)
    
    try:
        print(f"🤖 AI анализирует запрос: {user_message}")
        
        result = ai_classifier(user_message[:512])
        ai_label = result[0]['label']
        ai_confidence = result[0]['score']
        
        print(f"🎯 AI определил: {ai_label} (уверенность: {ai_confidence:.2f})")
        
        keywords = extract_keywords_advanced(user_message)
        
        if ai_confidence > 0.7:
            if ai_label in ['joy', 'surprise', 'neutral']:
                keywords['ai_mood'] = 'positive'
                keywords['response_tone'] = 'enthusiastic'
            elif ai_label in ['sadness', 'anger', 'fear']:
                keywords['ai_mood'] = 'negative' 
                keywords['response_tone'] = 'supportive'
        
        print(f"🔍 AI анализ завершен: {keywords}")
        
        return keywords
        
    except Exception as e:
        print(f"⚠️ AI анализ не сработал: {e}")
        return extract_keywords_advanced(user_message)

def extract_keywords_advanced(user_message):
    """ПРОДВИНУТЫЙ анализ запроса с приоритетом для дней недели"""
    message_lower = user_message.lower()
    
    print(f"🔍 Анализирую запрос: {user_message}")
    
    # 1. Сначала ищем ДНИ НЕДЕЛИ
    specific_day = None
    next_week = False
    this_week = False
    
    days_mapping = {
        'понедельник': 'понедельник', 'пн': 'понедельник',
        'вторник': 'вторник', 'вт': 'вторник',
        'среда': 'среда', 'ср': 'среда', 'среду': 'среда',
        'четверг': 'четверг', 'чт': 'четверг', 'четвер': 'четверг',
        'пятница': 'пятница', 'пт': 'пятница', 'пятницу': 'пятница', 
        'суббота': 'суббота', 'сб': 'суббота', 'субботу': 'суббота',
        'воскресенье': 'воскресенье', 'вс': 'воскресенье'
    }
    
    for pattern, day_name in days_mapping.items():
        if pattern in message_lower:
            specific_day = day_name
            print(f"📅 Найден день: {specific_day}")
            break
    
    # Определяем период поиска
    next_week = any(word in message_lower for word in ['следующ', 'next', 'будущ', 'на следующей'])
    this_week = any(word in message_lower for word in ['этой', 'эту неделю', 'на этой'])
    
    # 2. Определяем общую категорию дней
    days_pref = 'любые'
    if specific_day:
        days_pref = 'конкретный'
    else:
        if any(word in message_lower for word in ['будн', 'рабоч', 'пн-пт']):
            days_pref = 'будни'
        elif any(word in message_lower for word in ['выходн', 'уикенд', 'сб', 'суббот', 'воскресен']):
            days_pref = 'выходные'
    
    # 3. Ищем время
    time_pref = 'любое'
    time_keywords = {
        'утро': ['утро', 'утром', 'утрен', 'рано', 'с утра'],
        'обед': ['обед', 'обеден', 'день', 'дневн', 'после обеда', 'в обед'],
        'вечер': ['вечер', 'вечером', 'поздн', 'после работ', 'после работы']
    }
    
    for time_key, keywords in time_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            time_pref = time_key
            break
    
    # 4. Ищем дисциплину
    discipline = None
    discipline_keywords = {
        'nlp': ['nlp', 'естествен', 'язык', 'обработк', 'лингвист', 'текст'],
        'бизнес': ['бизнес', 'аналитик', 'инструмент', 'анализ данн', 'bi'],
        'спорт': ['спорт', 'анализ', 'соревнован', 'матч'],
        'проект': ['проект', 'практикум', 'разработк', 'программир'],
        'практика': ['практика', 'вебинар', 'ментор', 'встреч']
    }
    
    for disc, keywords in discipline_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            discipline = disc
            break
    
    # 5. Определяем тип запроса
    request_type = 'слоты'
    if any(word in message_lower for word in ['окошк', 'окно', 'окошечк']):
        request_type = 'окошка'
    elif any(word in message_lower for word in ['заняти', 'урок', 'лекци', 'семинар']):
        request_type = 'занятия'
    
    result = {
        'discipline': discipline,
        'time': time_pref, 
        'days': days_pref,
        'specific_day': specific_day,
        'next_week': next_week,
        'this_week': this_week,
        'request_type': request_type,
        'ai_mood': 'neutral',
        'response_tone': 'neutral'
    }
    
    print(f"🎯 Результат анализа: {result}")
    return result

def find_free_slots_for_ai(discipline=None, time_pref='любое', days_pref='любые', 
                          specific_day=None, next_week=False, this_week=False, days_ahead=30):
    """Умный поиск слотов для AI запросов"""
    
    time_mapping = {
        'утро': ['10:15-11:45'],
        'обед': ['12:00-13:30', '14:15-15:45'],
        'вечер': ['16:00-17:30', '17:40-19:05', '19:15-20:40', '20:45-22:10'],
        'любое': TIME_SLOTS
    }
    
    day_mapping = {
        'будни': ['понедельник', 'вторник', 'среда', 'четверг', 'пятница'],
        'выходные': ['суббота'],
        'любые': ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'],
        'конкретный': [specific_day] if specific_day else []
    }
    
    target_times = time_mapping.get(time_pref, TIME_SLOTS)
    target_days = day_mapping.get(days_pref, day_mapping['любые'])
    
    # ЗАГРУЖАЕМ ЗАНЯТЫЕ СЛОТЫ ПРАВИЛЬНО
    busy_slots = get_busy_slots()
    
    free_slots = []
    today = datetime.now()
    
    print(f"🔍 Поиск слотов: день={specific_day}, след.неделя={next_week}, время={time_pref}")
    
    # ОГРАНИЧИВАЕМ поиск 30 днями (1 месяц)
    for i in range(min(days_ahead, 30)):
        current_date = today + timedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        
        day_name = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][current_date.weekday()]
        
        if day_name == "воскресенье":
            continue
        
        # ПРОВЕРЯЕМ КРИТЕРИИ ПОИСКА
        skip_day = False
        
        if specific_day:
            if day_name != specific_day:
                skip_day = True
            elif next_week and current_date.isocalendar()[1] <= today.isocalendar()[1]:
                skip_day = True
            elif this_week and current_date.isocalendar()[1] != today.isocalendar()[1]:
                skip_day = True
        else:
            if day_name not in target_days:
                skip_day = True
        
        if skip_day:
            continue
        
        # ПРОВЕРЯЕМ ЗАНЯТЫЕ СЛОТЫ ДЛЯ ЭТОЙ ДАТЫ
        occupied = busy_slots.get(date_str, [])
        
        for time_slot in target_times:
            if time_slot not in occupied:
                free_slots.append({
                    'date': date_str,
                    'day': day_name, 
                    'time': time_slot,
                    'discipline': discipline
                })
    
    print(f"✅ Найдено свободных слотов: {len(free_slots)}")
    return free_slots

def generate_ai_response(keywords, free_slots, user_message):
    """Умный ответ с учетом AI анализа"""
    
    tone_emojis = {
        'enthusiastic': '🎉',
        'supportive': '🤗', 
        'neutral': '🤖'
    }
    emoji = tone_emojis.get(keywords.get('response_tone', 'neutral'), '🤖')
    
    discipline_names = {
        'nlp': 'Обработка естественного языка',
        'бизнес': 'Инструменты бизнес-аналитики',
        'спорт': 'Спортивный анализ',
        'проект': 'Проектный практикум',
        'praктика': 'Практика',
        None: 'любая дисциплина'
    }
    
    time_names = {
        'утро': 'утреннее время',
        'обед': 'обеденное время',
        'вечер': 'вечернее время', 
        'любое': 'любое время'
    }
    
    response = f"{emoji} *AI нашел свободные {keywords['request_type']}:*\n\n"
    
    response += "*Критерии поиска:*\n"
    response += f"• Дисциплина: {discipline_names[keywords['discipline']]}\n"
    response += f"• Время: {time_names[keywords['time']]}\n"
    
    if keywords['specific_day']:
        if keywords['next_week']:
            response += f"• День: следующий {keywords['specific_day']}\n"
        elif keywords['this_week']:
            response += f"• День: {keywords['specific_day']} на этой неделе\n"
        else:
            response += f"• День: {keywords['specific_day']}\n"
    else:
        days_names = {
            'будни': 'будние дни (пн-пт)',
            'выходные': 'выходные дни (сб)',
            'любые': 'любые дни'
        }
        response += f"• Дни: {days_names[keywords['days']]}\n"
    
    response += f"• Период поиска: 30 дней\n\n"
    
    if free_slots:
        # Ограничиваем показ 10 слотами
        display_slots = free_slots[:10]
        
        response += f"*✅ Найдены свободные {keywords['request_type']}:*\n"
        for i, slot in enumerate(display_slots, 1):
            date_obj = datetime.strptime(slot['date'], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            response += f"{i}. {formatted_date} ({slot['day']}) - {slot['time']}\n"
        
        if len(free_slots) > len(display_slots):
            response += f"\n... и еще {len(free_slots) - len(display_slots)} слотов\n"
            
        response += f"\n🎯 Всего найдено: {len(free_slots)} {keywords['request_type']}\n"
        
        if keywords.get('ai_mood') == 'positive':
            response += "\n🌟 *Отлично! Есть варианты для записи!*"
        elif keywords.get('ai_mood') == 'negative':
            response += "\n💫 *Есть варианты! Рекомендую выбрать подходящий слот.*"
            
    else:
        response += f"❌ *Свободных {keywords['request_type']} не найдено*\n"
        response += "\n💡 *AI рекомендует:*\n"
        response += "• Попробуйте другой день недели\n"
        response += "• Измените время дня\n"
        response += "• Расширьте критерии поиска\n"
    
    response += f"\n_🤖 Поиск выполнен среди ближайших 30 дней_"
    
    return response

# ===== УМНЫЙ КАЛЕНДАРЬ С ЦВЕТНОЙ СИСТЕМОЙ =====
def create_calendar(year=None, month=None):
    """Создает календарь с умным отображением занятости - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    now = datetime.now()
    if year is None: 
        year = now.year
    if month is None: 
        month = now.month
    
    # Просто читаем занятые слоты без кэширования
    busy_slots = get_busy_slots()
    
    keyboard = []
    
    # Заголовок
    month_names = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    header = [InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="ignore")]
    keyboard.append(header)
    
    # Дни недели
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in days])
    
    # Ячейки календаря
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                day_of_week = date_obj.weekday()
                
                is_sunday = (day_of_week == 6)
                is_holiday_day = is_holiday(date_str)
                
                # Проверяем занятость
                occupied_times = busy_slots.get(date_str, [])
                total_slots = len(TIME_SLOTS)
                occupied_count = len(occupied_times)
                
                is_fully_busy = occupied_count >= total_slots
                is_partially_busy = occupied_count > 0 and not is_fully_busy
                is_free = occupied_count == 0
                
                # ВАЖНОЕ ИСПРАВЛЕНИЕ: используем правильный формат callback_data
                if is_sunday:
                    row.append(InlineKeyboardButton(f"⚪{day}", callback_data="ignore"))
                elif is_holiday_day:
                    row.append(InlineKeyboardButton(f"🔴{day}", callback_data="ignore"))
                elif is_fully_busy:
                    row.append(InlineKeyboardButton(f"❌{day}", callback_data="ignore"))
                elif is_partially_busy:
                    # День с частичной занятостью - можно выбирать!
                    row.append(InlineKeyboardButton(f"🟡{day}", callback_data=f"calendar_day_{year}_{month:02d}_{day:02d}"))
                else:
                    # Полностью свободный день
                    row.append(InlineKeyboardButton(f"✅{day}", callback_data=f"calendar_day_{year}_{month:02d}_{day:02d}"))
        keyboard.append(row)
    
    # Навигация
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year = year - 1
    
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year = year + 1
    
    navigation = []
    if prev_year >= 2024:
        navigation.append(InlineKeyboardButton("⬅️", callback_data=f"calendar_prev_{prev_year}_{prev_month:02d}"))
    else:
        navigation.append(InlineKeyboardButton(" ", callback_data="ignore"))
    
    navigation.append(InlineKeyboardButton(f"{year}", callback_data="ignore"))
    
    if next_year <= 2026:
        navigation.append(InlineKeyboardButton("➡️", callback_data=f"calendar_next_{next_year}_{next_month:02d}"))
    else:
        navigation.append(InlineKeyboardButton(" ", callback_data="ignore"))
    
    keyboard.append(navigation)
    
    # Легенда
    legend = [
        InlineKeyboardButton("✅ Свободен", callback_data="ignore"),
        InlineKeyboardButton("🟡 Частично", callback_data="ignore"),
        InlineKeyboardButton("❌ Занят", callback_data="ignore"),
        InlineKeyboardButton("🔴 Праздник", callback_data="ignore"),
        InlineKeyboardButton("⚪ Выходной", callback_data="ignore")
    ]
    keyboard.append(legend)
    
    return InlineKeyboardMarkup(keyboard)

def create_time_keyboard(date_str):
    """Создает клавиатуру для выбора времени со статистикой"""
    busy_slots = get_busy_slots()
    occupied_times = busy_slots.get(date_str, [])
    
    keyboard = []
    
    for time_slot in TIME_SLOTS:
        is_occupied = time_slot in occupied_times
        emoji = "⏰" if not is_occupied else "❌"
        status = " (свободно)" if not is_occupied else " (занято)"
        button_text = f"{emoji} {time_slot}{status}"
        
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f"time_{time_slot}" if not is_occupied else "ignore"
        )])
    
    # СТАТИСТИКА ПО ДНЮ
    free_count = len([t for t in TIME_SLOTS if t not in occupied_times])
    total_count = len(TIME_SLOTS)
    
    keyboard.append([InlineKeyboardButton(
        f"📊 Свободно слотов: {free_count}/{total_count}", 
        callback_data="ignore"
    )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад к календарю", callback_data="back_to_calendar")])
    
    return InlineKeyboardMarkup(keyboard)

def create_discipline_keyboard():
    """Создает клавиатуру для выбора дисциплины"""
    keyboard = []
    
    for i, discipline in enumerate(DISCIPLINES):
        short_name = discipline[:25] + "..." if len(discipline) > 25 else discipline
        keyboard.append([InlineKeyboardButton(short_name, callback_data=f"discipline_{i}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_time")])
    
    return InlineKeyboardMarkup(keyboard)

# ===== БАЗОВЫЕ ФУНКЦИИ БОТА =====
def init_excel():
    """Инициализация Excel файла"""
    if not os.path.exists(EXCEL_FILE):
        columns = ['Неделя', 'День', 'Дата', 'Время', 'Дисциплина', 'Занятие', 'Эксперт', 'Статус', 'Комментарий']
        df = pd.DataFrame(columns=columns)
        df.to_excel(EXCEL_FILE, index=False)
        print("✅ Создан новый файл расписания")

def read_schedule():
    """Чтение расписания из Excel с обработкой разных формаats"""
    try:
        df = pd.read_excel(EXCEL_FILE)
        
        # Отладочная информация
        if not df.empty:
            print(f"📖 Прочитано {len(df)} записей из Excel")
            print(f"📅 Диапазон дат в файле: {df['Дата'].min()} - {df['Дата'].max()}")
            
        return df
    except Exception as e:
        print(f"❌ Ошибка чтения Excel: {e}")
        return pd.DataFrame()

def save_schedule(df):
    """Сохранение расписания в Excel"""
    try:
        df.to_excel(EXCEL_FILE, index=False)
        return True
    except Exception as e:
        print(f"Ошибка сохранения Excel: {e}")
        return False

def get_busy_slots():
    """Правильно читает занятые слоты из Excel"""
    df = read_schedule()
    busy_slots = {}
    
    for _, row in df.iterrows():
        if pd.notna(row.get('Дата')) and pd.notna(row.get('Время')):
            date_str = str(row['Дата'])
            
            # ПРАВИЛЬНО обрабатываем разные форматы дат из Excel
            try:
                # Если дата в формате datetime
                if isinstance(date_str, str) and len(date_str) > 10:
                    date_str = date_str.split()[0]  # Берем только дату
                
                # Преобразуем в стандартный формат
                date_obj = None
                if '-' in date_str and len(date_str) == 10:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                elif '.' in date_str:
                    date_obj = datetime.strptime(date_str, "%Y.%m.%d")
                else:
                    # Пробуем разные форматы
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    except:
                        date_obj = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
                
                if date_obj:
                    date_str_final = date_obj.strftime("%Y-%m-%d")
                    
                    if date_str_final not in busy_slots:
                        busy_slots[date_str_final] = []
                    busy_slots[date_str_final].append(row['Время'])
                    
            except Exception as e:
                print(f"⚠️ Ошибка обработки даты '{date_str}': {e}")
                continue
    
    print(f"📊 Загружено занятых дней: {len(busy_slots)}")
    return busy_slots

def debug_busy_slots(month=None, year=None):
    """Отладочная функция для проверки занятости"""
    busy_slots = get_busy_slots()
    
    if month and year:
        print(f"🔍 Проверка занятости для {month}.{year}:")
        for date_str, times in busy_slots.items():
            if date_str.startswith(f"{year}-{month:02d}"):
                print(f"   {date_str}: {len(times)} занятых слотов - {times}")
    else:
        print("📊 Все занятые слоты:")
        for date_str, times in sorted(busy_slots.items()):
            print(f"   {date_str}: {len(times)} занятых слотов")
    
    return busy_slots

def add_schedule_entry(week, day, date, time_slot, discipline, lesson_num, expert, status="черновик", comment=""):
    """Добавление записи в расписание"""
    df = read_schedule()
    
    new_entry = {
        'Неделя': week,
        'День': day,
        'Дата': date,
        'Время': time_slot,
        'Дисциплина': discipline,
        'Занятие': lesson_num,
        'Эксперт': expert,
        'Статус': status,
        'Комментарий': comment
    }
    
    df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    return save_schedule(df)

def get_main_keyboard():
    """Главное меню с кнопкой AI поиска"""
    return ReplyKeyboardMarkup([
        ['📅 Выбрать даты занятий', '🔍 Найти свободную дату'],
        ['👀 Посмотреть расписание', '❓ Помощь'],
        ['/start - Главное меню']  # Добавляем кнопку для возврата в меню
    ], resize_keyboard=True)

# ===== ОБРАБОТЧИКИ БОТА =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - возврат в главное меню"""
    user_id = update.message.from_user.id
    
    # Сбрасываем состояние ожидания комментария
    if user_id in user_data:
        user_data[user_id]['waiting_for_comment'] = False
    
    await update.message.reply_text(
        "🎓 *Бот-составитель расписания с AI*\n\n"
        "🤖 *Работает настоящая AI модель!*\n"
        "🎨 *Умная цветная система календаря*\n\n"
        "Используйте кнопки меню:",
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def handle_ai_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик AI поиска с РАБОЧЕЙ моделью"""
    user_message = update.message.text
    
    if user_message == '🔍 Найти свободную дату':
        await update.message.reply_text(
            "🔍 *AI-поиск свободных слотов*\n\n"
            "Напишите запрос, например:\n"
            "• 'свободные слоты в субботу'\n" 
            "• 'окна на следующей неделе'\n"
            "• 'занятия вечером в среду'\n"
            "• 'свободные окошки в пятницу'\n"
            "• 'найди свободное время на следующий вторник'\n\n"
            "🤖 AI модель проанализирует ваш запрос!",
            parse_mode='Markdown'
        )
    else:
        processing_msg = await update.message.reply_text("🤖 AI анализирует ваш запрос...")
        
        try:
            keywords = smart_ai_analysis(user_message)
            
            free_slots = find_free_slots_for_ai(
                discipline=keywords['discipline'],
                time_pref=keywords['time'],
                days_pref=keywords['days'],
                specific_day=keywords['specific_day'],
                next_week=keywords['next_week'],
                this_week=keywords['this_week']
            )
            
            response = generate_ai_response(keywords, free_slots, user_message)
            
            await context.bot.edit_message_text(
                chat_id=processing_msg.chat_id,
                message_id=processing_msg.message_id,
                text=response,
                parse_mode='Markdown'
            )
            
            # СРАЗУ показываем главное меню после ответа AI
            await update.message.reply_text(
                "Используйте кнопки меню для дальнейших действий:",
                reply_markup=get_main_keyboard()
            )
            
        except Exception as e:
            error_msg = f"❌ Ошибка AI поиска: {str(e)}"
            await context.bot.edit_message_text(
                chat_id=processing_msg.chat_id,
                message_id=processing_msg.message_id, 
                text=error_msg
            )
            await update.message.reply_text(
                "Используйте кнопки меню:",
                reply_markup=get_main_keyboard()
            )

async def show_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ календаря с цветной системой"""
    calendar_markup = create_calendar()
    await update.message.reply_text(
        "📅 *Выберите дату занятия:*\n\n"
        "🎨 *Умная цветная система:*\n"
        "✅ - день полностью свободен\n"
        "🟡 - есть свободные слоты (можно выбирать!)\n" 
        "❌ - день полностью занят\n"
        "🔴 - праздничный день\n"
        "⚪ - воскресенье\n\n"
        "*Выбирайте дни с 🟡 и ✅*",
        reply_markup=calendar_markup,
        parse_mode='Markdown'
    )

async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка календаря - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    print(f"🔍 Обрабатываю callback: {data}")  # Отладочная информация
    
    if data.startswith("calendar_day_"):
        try:
            # ИСПРАВЛЕНИЕ: правильный парсинг callback_data
            parts = data.split("_")
            year = int(parts[2])
            month = int(parts[3])
            day = int(parts[4])
            
            date_str = f"{year}-{month:02d}-{day:02d}"
            
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            is_sunday = (date_obj.weekday() == 6)
            is_holiday_day = is_holiday(date_str)
            
            if is_sunday or is_holiday_day:
                reason = "воскресенье" if is_sunday else "праздничный день"
                await query.answer(f"❌ {day:02d}.{month:02d}.{year} - {reason}, занятия не проводятся", show_alert=True)
                return
            
            # Сохраняем выбранную дату
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['selected_date'] = date_str
            
            # Создаем клавиатуру времени
            time_keyboard = create_time_keyboard(date_str)
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            await query.edit_message_text(
                f"🕐 *Выберите время для {formatted_date}:*\n\n"
                f"⏰ - свободное время\n"
                f"❌ - время занято\n\n"
                f"*Внизу показана статистика по дню*",
                reply_markup=time_keyboard,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            print(f"❌ Ошибка обработки даты: {e}")
            await query.answer("❌ Ошибка выбора даты", show_alert=True)
    
    elif data.startswith("calendar_prev_"):
        try:
            parts = data.split("_")
            year = int(parts[2])
            month = int(parts[3])
            calendar_markup = create_calendar(year, month)
            await query.edit_message_reply_markup(reply_markup=calendar_markup)
        except Exception as e:
            print(f"❌ Ошибка навигации назад: {e}")
    
    elif data.startswith("calendar_next_"):
        try:
            parts = data.split("_")
            year = int(parts[2])
            month = int(parts[3])
            calendar_markup = create_calendar(year, month)
            await query.edit_message_reply_markup(reply_markup=calendar_markup)
        except Exception as e:
            print(f"❌ Ошибка навигации вперед: {e}")
    
    elif data == "back_to_calendar":
        calendar_markup = create_calendar()
        await query.edit_message_text(
            "📅 *Выберите дату занятия:*\n\n"
            "🎨 *Умная цветная система:*\n"
            "✅ - день полностью свободен\n"
            "🟡 - есть свободные слоты (можно выбирать!)\n" 
            "❌ - день полностью занят\n"
            "🔴 - праздничный день\n"
            "⚪ - воскресенье\n\n"
            "*Выбирайте дни с 🟡 и ✅*",
            reply_markup=calendar_markup,
            parse_mode='Markdown'
        )
    
    else:
        print(f"⚠️ Неизвестный callback: {data}")

async def handle_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data.startswith("time_"):
        time_slot = query.data[5:]
        
        if user_id in user_data and 'selected_date' in user_data[user_id]:
            date_str = user_data[user_id]['selected_date']
            user_data[user_id]['selected_time'] = time_slot
            
            discipline_keyboard = create_discipline_keyboard()
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            await query.edit_message_text(
                f"📚 *Выберите дисциплину:*\n\n"
                f"📅 Дата: {formatted_date}\n"
                f"🕐 Время: {time_slot}",
                reply_markup=discipline_keyboard,
                parse_mode='Markdown'
            )
    
    elif query.data == "back_to_time":
        if user_id in user_data and 'selected_date' in user_data[user_id]:
            date_str = user_data[user_id]['selected_date']
            time_keyboard = create_time_keyboard(date_str)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            await query.edit_message_text(f"🕐 Выберите время для {formatted_date}:", reply_markup=time_keyboard)

async def handle_discipline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора дисциплины"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data.startswith("discipline_"):
        discipline_index = int(query.data.split("_")[1])
        discipline_name = DISCIPLINES[discipline_index]
        
        if user_id in user_data and 'selected_date' in user_data[user_id] and 'selected_time' in user_data[user_id]:
            user_data[user_id]['selected_discipline'] = discipline_name
            
            expert_name = f"{query.from_user.first_name} {query.from_user.last_name or ''}".strip()
            user_data[user_id]['expert_name'] = expert_name
            
            date_str = user_data[user_id]['selected_date']
            time_slot = user_data[user_id]['selected_time']
            
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            day_of_week = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][date_obj.weekday()]
            week_num = f"Неделя {(date_obj.day - 1) // 7 + 1}"
            
            success = add_schedule_entry(
                week=week_num,
                day=day_of_week,
                date=date_str,
                time_slot=time_slot,
                discipline=discipline_name,
                lesson_num="1",
                expert=expert_name,
                comment=""
            )
            
            if success:
                user_data[user_id]['waiting_for_comment'] = True
                formatted_date = date_obj.strftime("%d.%m.%Y")
                
                await query.edit_message_text(
                    f"✅ *Успешно добавлено!*\n\n"
                    f"📅 Дата: {formatted_date}\n"
                    f"🕐 Время: {time_slot}\n"
                    f"📚 Дисциплина: {discipline_name}\n"
                    f"👨‍🏫 Эксперт: {expert_name}\n\n"
                    f"💡 Хотите добавить комментарий?\n"
                    f"Напишите его сейчас или нажмите /start для возврата в меню.",
                    parse_mode='Markdown'
                )
                
                # СРАЗУ показываем главное меню
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="Используйте кнопки меню для дальнейших действий:",
                    reply_markup=get_main_keyboard()
                )
            else:
                await query.edit_message_text("❌ Ошибка при сохранении")
    
    elif query.data == "back_to_time":
        if user_id in user_data and 'selected_date' in user_data[user_id]:
            date_str = user_data[user_id]['selected_date']
            time_keyboard = create_time_keyboard(date_str)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            await query.edit_message_text(f"🕐 Выберите время для {formatted_date}:", reply_markup=time_keyboard)

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка комментариев"""
    user_id = update.message.from_user.id
    text = update.message.text
    
    if user_id in user_data and user_data[user_id].get('waiting_for_comment'):
        if text and text not in ['/start', '📅 Выбрать даты занятий', '👀 Посмотреть расписание', '❓ Помощь', '🔍 Найти свободную дату']:
            df = read_schedule()
            if not df.empty:
                mask = (df['Эксперт'] == user_data[user_id]['expert_name']) & \
                       (df['Дата'] == user_data[user_id]['selected_date']) & \
                       (df['Время'] == user_data[user_id]['selected_time'])
                if mask.any():
                    df.loc[mask, 'Комментарий'] = text
                    save_schedule(df)
            
            message = f"💬 *Комментарий добавлен!*\n\nВаш комментарий: {text}\n\n"
        else:
            message = "✅ *Запись сохранена без комментария*\n\n"
        
        user_data[user_id]['waiting_for_comment'] = False
        
        # СРАЗУ возвращаем в главное меню
        await update.message.reply_text(
            message + "Возвращаю в главное меню:",
            reply_markup=get_main_keyboard()
        )
    else:
        await handle_ai_search(update, context)

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ расписания"""
    try:
        df = read_schedule()
        if df.empty:
            await update.message.reply_text("📭 Расписание пока пустое")
        else:
            schedule_text = "📅 *Текущее расписание:*\n\n"
            for _, row in df.iterrows():
                date_str = str(row['Дата']).split()[0]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                
                schedule_text += f"📌 {formatted_date} {row['Время']}\n"
                schedule_text += f"   🎯 {row['Дисциплина']}\n"
                schedule_text += f"   👨‍🏫 {row['Эксперт']}\n"
                schedule_text += f"   📊 Статус: {row['Статус']}\n"
                if pd.notna(row.get('Комментарий')) and row['Комментарий'] != "":
                    schedule_text += f"   💬 Комментарий: {row['Комментарий']}\n"
                schedule_text += "\n"
            
            await update.message.reply_text(schedule_text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка загрузки расписания: {e}")

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    await update.message.reply_text(
        "🤖 *Помощь по боту:*\n\n"
        "*Кнопки меню:*\n"
        "• 📅 Выбрать даты - интерактивный календарь\n"
        "• 🔍 Найти свободную дату - AI поиск слотов\n"
        "• 👀 Расписание - просмотр всех занятий\n"
        "• /start - вернуться в главное меню\n\n"
        "*AI поиск:*\n"
        "Напишите запрос в свободной форме:\n"
        "'свободные слоты в субботу'\n"
        "'окна на следующей неделе'\n" 
        "'занятия вечером в среду'\n"
        "'найди свободное время на следующий вторник'\n\n"
        "*🎨 Цвета календаря:*\n"
        "✅ - свободен (0 занятых слотов)\n"
        "🟡 - частично занят (1-6 занятых слотов)\n" 
        "❌ - полностью занят (7 занятых слотов)\n"
        "🔴 - праздник\n"
        "⚪ - воскресенье",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех сообщений"""
    user_id = update.message.from_user.id
    text = update.message.text
    
    if user_id in user_data and user_data[user_id].get('waiting_for_comment'):
        await handle_comment(update, context)
        return
    
    # Добавляем отладочную команду
    if text == '/debug':
        await handle_debug(update, context)
        return
    
    if text == '🔍 Найти свободную дату':
        await handle_ai_search(update, context)
    elif text == '📅 Выбрать даты занятий':
        await show_calendar(update, context)
    elif text == '👀 Посмотреть расписание':
        await show_schedule(update, context)
    elif text == '❓ Помощь':
        await handle_help(update, context)
    elif text == '/start':
        await start(update, context)
    else:
        await handle_ai_search(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте еще раз или используйте /start",
            reply_markup=get_main_keyboard()
        )

async def handle_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отладочная команда для проверки занятости"""
    busy_slots = debug_busy_slots()
    
    response = "🐛 *Отладочная информация:*\n\n"
    response += f"📊 Всего занятых дней: {len(busy_slots)}\n"
    
    # Показываем последние 10 занятых дней
    sorted_dates = sorted(busy_slots.keys())[-10:]
    for date_str in sorted_dates:
        times = busy_slots[date_str]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d.%m.%Y")
        response += f"📅 {formatted_date}: {len(times)} занятых слотов\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

# ===== ЗАПУСК БОТА =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_data = {}

def main():
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        application.add_handler(CallbackQueryHandler(handle_calendar_callback, pattern="^calendar_"))
        application.add_handler(CallbackQueryHandler(handle_time_callback, pattern="^time_"))
        application.add_handler(CallbackQueryHandler(handle_discipline_callback, pattern="^discipline_"))
        application.add_handler(CallbackQueryHandler(handle_calendar_callback, pattern="^back_to_calendar"))
        application.add_handler(CallbackQueryHandler(handle_time_callback, pattern="^back_to_time"))
        
        application.add_error_handler(error_handler)
        
        print("=" * 60)
        print("🤖 Бот запущен с РАБОЧЕЙ AI моделью!")
        print("🎯 Исправления:")
        print("   • Даты в календаре теперь нажимаются!")
        print("   • 'Следующий вторник' - показывается только один день")
        print("   • Поиск ограничен 30 днями")
        print("   • Добавлена кнопка /start для возврата в меню")
        print("🎨 Умная цветная система календаря")
        print("=" * 60)
        
        # Запускаем бота с обработкой KeyboardInterrupt
        application.run_polling()
        
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        print("👋 Бот завершил работу")

if __name__ == "__main__":
    init_excel()
    
    # Для Jupyter/Colab используем такой запуск
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")