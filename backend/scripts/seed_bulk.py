"""Fills the stand with a catalogue big enough to be worth searching.

    docker compose up -d
    docker compose exec backend python -m scripts.seed_bulk            # ~60 shops, ~2000 products
    docker compose exec backend python -m scripts.seed_bulk --reset    # drop the previous batch

Unlike scripts/seed_demo.py, which walks the public API the way a person would, this one
writes straight to the database and to object storage: two thousand products through HTTP
would take an hour and prove nothing the demo seed has not already proven.

Everything it creates carries the @fake.allstore.am email domain, which is the handle
--reset pulls. Real accounts and the data of scripts/seed_demo.py are never touched.
"""

import argparse
import asyncio
import os
import random
import struct
import sys
import threading
import uuid
import zlib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

# the defaults of the compose stack, so the script runs with no shell setup
_DEFAULTS = {
    "APP_ENV": "local",
    "SECRET_KEY": "dev-secret-change-me-not-for-production",
    "DATABASE_URL": "postgresql+asyncpg://allstore:allstore@localhost:5433/allstore",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "minioadmin",
    "S3_SECRET_KEY": "minioadmin",
    "S3_BUCKET": "allstore-dev",
}
for _key, _value in _DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.storage import build_s3_client, public_url  # noqa: E402
from app.models import (  # noqa: E402
    Business,
    BusinessModerationReview,
    BusinessStatus,
    Category,
    ModerationReview,
    ModerationStatus,
    Product,
    ProductAvailability,
    ProductImage,
    PublicationStatus,
    Report,
    ReportStatus,
    SocialLink,
    Store,
    StoreStatus,
    User,
    UserRole,
)
from app.models.contact import ContactPlatform  # noqa: E402
from app.models.moderation import BusinessDecision, ModerationDecision  # noqa: E402

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

# one password for every generated account; this stack is local only
PASSWORD = "demo-password-1"  # noqa: S105
# the handle --reset pulls: everything this script creates lives under it
DOMAIN = "fake.allstore.am"
IMAGE_SIDE = 480
CATALOGUE_AGE_DAYS = 240

Colour = tuple[int, int, int]


@dataclass(frozen=True)
class Kind:
    """The vocabulary of one leaf category.

    `items` are whole noun phrases and `attrs` are postfix phrases, so a name is assembled
    without having to agree adjectives with nouns. `materials` are in the genitive because
    the description puts them after "сделано из"; `uses` are whole clauses for the same
    reason — generated Russian that does not parse is worse than no text at all.
    """

    items: tuple[str, ...]
    attrs: tuple[str, ...]
    materials: tuple[str, ...]
    uses: tuple[str, ...]
    price: tuple[int, int]
    palette: tuple[Colour, ...]


WARM = ((198, 128, 92), (238, 214, 186), (176, 96, 74))
COOL = ((92, 124, 168), (186, 208, 232), (72, 96, 136))
GREEN = ((104, 142, 96), (206, 222, 190), (76, 110, 72))
DARK = ((64, 68, 84), (128, 134, 156), (44, 48, 62))
BRIGHT = ((186, 72, 96), (240, 186, 196), (150, 48, 76))

# Armenian place names, used as product and shop titles
TITLES = (
    "Арарат",
    "Севан",
    "Гюмри",
    "Дилижан",
    "Татев",
    "Гарни",
    "Эребуни",
    "Лори",
    "Ани",
    "Звартноц",
    "Ширак",
    "Вайоц",
    "Аштарак",
    "Джермук",
)

COLOURS = (
    "белый",
    "чёрный",
    "бежевый",
    "терракотовый",
    "изумрудный",
    "синий",
    "песочный",
    "графитовый",
    "бордовый",
    "оливковый",
)

CLOSERS = (
    "Отправляем из Еревана в день заказа.",
    "Возможен самовывоз в центре города.",
    "Упакуем как подарок бесплатно.",
    "Даём гарантию 12 месяцев.",
    "Есть другие размеры и цвета — спрашивайте в сообщениях.",
    "Делаем под заказ, срок — до пяти дней.",
    "Доставка по Армении, оплата при получении.",
)

KINDS: dict[str, Kind] = {
    "toys": Kind(
        ("Конструктор", "Мягкая игрушка", "Настольная игра", "Кукла", "Машинка", "Пазл"),
        ("ручной работы", "на 120 деталей", "в подарочной коробке", "для малышей", "с подсветкой"),
        ("бука", "хлопка", "безопасного пластика", "фетра", "липы"),
        (
            "Подойдёт ребёнку от трёх лет",
            "Развивает мелкую моторику и усидчивость",
            "Хорошо идёт в подарок на день рождения",
        ),
        (2000, 28000),
        BRIGHT,
    ),
    "baby-care": Kind(
        ("Пелёнка", "Бутылочка", "Слюнявчик", "Комплект в кроватку", "Полотенце с капюшоном"),
        ("из муслина", "набор из трёх штук", "с вышивкой", "0+", "без красителей"),
        ("муслина", "органического хлопка", "бамбукового волокна", "мягкой махры"),
        (
            "Подходит для новорождённых с первых дней",
            "Выдерживает частую стирку и не теряет цвет",
            "Удобно брать с собой в поездку",
        ),
        (1500, 18000),
        COOL,
    ),
    "furniture": Kind(
        ("Стол обеденный", "Стул", "Полка настенная", "Комод", "Тумба", "Кресло"),
        ("из массива", "в скандинавском стиле", "на металлических ножках", "с ящиками"),
        ("дуба", "бука", "ясеня", "массива сосны", "шпона ореха"),
        (
            "Впишется в небольшую гостиную",
            "Удобно для кухни и столовой",
            "Собирается за полчаса, инструмент в комплекте",
        ),
        (25000, 480000),
        WARM,
    ),
    "tableware": Kind(
        ("Ваза", "Кружка", "Тарелка глубокая", "Салатник", "Чайник заварочный", "Набор пиал"),
        ("ручной работы", "высота 30 см", "набор 4 шт.", "с росписью", "объём 350 мл"),
        ("керамики", "фарфора", "жаропрочного стекла", "глины ручной формовки"),
        (
            "Подойдёт для сервировки и для подарка",
            "Можно мыть в посудомоечной машине",
            "Хорошо смотрится на открытой полке",
        ),
        (2500, 45000),
        WARM,
    ),
    "garden": Kind(
        ("Секатор", "Лейка", "Набор семян", "Кашпо", "Садовые перчатки", "Шланг поливочный"),
        ("15 м", "набор из пяти штук", "с антискользящим покрытием", "для балкона"),
        ("нержавеющей стали", "глины", "армированного ПВХ", "переработанного пластика"),
        (
            "Пригодится и на даче, и на балконе",
            "Не боится солнца и дождя",
            "Лёгкий, не устаёт рука при долгой работе",
        ),
        (1200, 32000),
        GREEN,
    ),
    "home-textiles": Kind(
        ("Плед", "Скатерть", "Комплект постельного белья", "Полотенце", "Штора", "Ковёр"),
        ("140×240", "на двуспальную кровать", "из льна", "ручного ткачества", "150×200"),
        ("льна", "хлопка", "шерсти", "смесовой пряжи", "жаккарда"),
        (
            "Согреет прохладным вечером на террасе",
            "Подойдёт к светлому интерьеру",
            "Не линяет и не мнётся после стирки",
        ),
        (4000, 260000),
        WARM,
    ),
    "pet-food": Kind(
        ("Корм для кошек", "Корм для собак", "Лакомство", "Наполнитель", "Витамины"),
        ("2 кг", "с ягнёнком", "без злаков", "для щенков", "без искусственных добавок"),
        ("натурального мяса", "риса и овощей", "древесных гранул"),
        (
            "Подходит для взрослых животных и пожилых",
            "Не вызывает расстройства при переходе на новый рацион",
            "Хватает примерно на месяц среднему питомцу",
        ),
        (1800, 24000),
        GREEN,
    ),
    "cosmetics": Kind(
        ("Крем для лица", "Сыворотка", "Маска тканевая", "Тональная основа", "Бальзам для губ"),
        ("50 мл", "с гиалуроновой кислотой", "для сухой кожи", "набор из пяти штук", "SPF 30"),
        ("натуральных масел", "растительных экстрактов", "гиалуроновой кислоты"),
        (
            "Подойдёт для ежедневного ухода",
            "Не оставляет липкой плёнки",
            "Можно наносить под макияж",
        ),
        (2500, 38000),
        BRIGHT,
    ),
    "perfume": Kind(
        ("Парфюмерная вода", "Туалетная вода", "Масляные духи", "Ароматическая свеча"),
        ("50 мл", "с древесными нотами", "с нотами цитруса", "унисекс", "в подарочной упаковке"),
        ("натуральных эфирных масел", "соевого воска", "смолы и специй"),
        (
            "Держится на коже весь день",
            "Подойдёт для вечера и для подарка",
            "Раскрывается постепенно, без резкого старта",
        ),
        (6000, 95000),
        DARK,
    ),
    "personal-care": Kind(
        ("Шампунь", "Мыло ручной работы", "Скраб для тела", "Гель для душа", "Зубная паста"),
        ("400 мл", "без сульфатов", "с гранатом", "набор из трёх штук"),
        ("оливкового масла", "мёда и трав", "морской соли", "растительных ПАВ"),
        (
            "Подходит для чувствительной кожи",
            "Хорошо пенится и легко смывается",
            "Приятный запах, который не перебивает духи",
        ),
        (1200, 16000),
        GREEN,
    ),
    "kids-clothing": Kind(
        ("Комбинезон", "Футболка детская", "Платье для девочки", "Куртка", "Пижама"),
        ("рост 98 см", "на 2–3 года", "из хлопка", "с начёсом", "на зиму"),
        ("хлопка", "флиса", "трикотажа", "мембранной ткани"),
        (
            "Не сковывает движения на прогулке",
            "Легко надевается и застёгивается",
            "Переживает частую стирку",
        ),
        (2500, 32000),
        BRIGHT,
    ),
    "womens-clothing": Kind(
        ("Платье", "Блузка", "Юбка", "Пальто", "Кардиган", "Брюки"),
        ("размер 46", "из вискозы", "миди", "оверсайз", "на подкладке"),
        ("вискозы", "льна", "шерсти с кашемиром", "плотного трикотажа"),
        (
            "Подойдёт и в офис, и на встречу вечером",
            "Садится по фигуре и не тянет в плечах",
            "Сочетается с базовым гардеробом",
        ),
        (6000, 180000),
        WARM,
    ),
    "mens-clothing": Kind(
        ("Рубашка", "Худи", "Джинсы", "Пиджак", "Свитер", "Футболка"),
        ("размер 50", "из хлопка", "прямого кроя", "на молнии", "с начёсом"),
        ("хлопка", "денима", "шерсти мериноса", "плотного джерси"),
        (
            "Подойдёт для работы и для выходных",
            "Не растягивается после стирки",
            "Ткань держит форму весь день",
        ),
        (5000, 160000),
        DARK,
    ),
    "footwear": Kind(
        ("Кроссовки", "Ботинки", "Туфли", "Сандалии", "Кеды", "Сапоги"),
        ("размер 41", "из натуральной кожи", "на протекторе", "на весну и осень", "на танкетке"),
        ("натуральной кожи", "замши", "текстиля с сеткой", "каучука"),
        (
            "Нога не устаёт при долгой ходьбе",
            "Подошва не скользит на мокром асфальте",
            "Подойдёт для города и лёгких прогулок",
        ),
        (9000, 140000),
        DARK,
    ),
    "groceries": Kind(
        ("Гречка", "Оливковое масло", "Мука", "Специи", "Мёд", "Сухофрукты"),
        ("1 кг", "500 мл", "набор из шести штук", "с горных пасек", "без сахара"),
        ("местного урожая", "первого отжима", "цельного зерна", "высокогорных пасек"),
        (
            "Подойдёт для ежедневной готовки",
            "Хранится долго, без холодильника",
            "Хорошо идёт как гостинец",
        ),
        (700, 18000),
        GREEN,
    ),
    "beverages": Kind(
        ("Гранатовый сок", "Горный чай", "Кофе в зёрнах", "Минеральная вода", "Компот"),
        ("1 л", "250 г", "без сахара", "средней обжарки", "упаковка 6 шт."),
        ("отжатых гранатов", "горных трав", "арабики", "природного источника"),
        (
            "Хорошо освежает в жару",
            "Подойдёт к завтраку и к десерту",
            "Вкус не приторный, без химического послевкусия",
        ),
        (600, 14000),
        BRIGHT,
    ),
    "sweets": Kind(
        ("Пахлава", "Суджух ореховый", "Варенье", "Гата", "Шоколад ручной работы", "Халва"),
        ("500 г", "набор из трёх штук", "по домашнему рецепту", "с грецким орехом"),
        ("мёда и орехов", "виноградного сока", "натурального какао", "домашнего теста"),
        (
            "Подойдёт к чаю и в подарок",
            "Готовим небольшими партиями, без консервантов",
            "Хранится две недели в прохладном месте",
        ),
        (1500, 16000),
        WARM,
    ),
    "bags-and-accessories": Kind(
        ("Сумка", "Рюкзак", "Кошелёк", "Ремень", "Шарф", "Перчатки"),
        ("из кожи", "формат A4", "ручной работы", "с внутренним карманом", "унисекс"),
        ("натуральной кожи", "плотного хлопка", "шерсти", "замши"),
        (
            "Помещается ноутбук и бутылка воды",
            "Подойдёт к деловому и к повседневному образу",
            "Фурнитура не темнеет со временем",
        ),
        (5000, 190000),
        DARK,
    ),
    "watches": Kind(
        ("Наручные часы", "Смарт-часы", "Настенные часы", "Песочные часы"),
        ("с кожаным ремешком", "водозащита 5 ATM", "с автоподзаводом", "диаметр 40 мм"),
        ("нержавеющей стали", "минерального стекла", "дерева", "сапфирового стекла"),
        (
            "Подойдёт под рубашку и под футболку",
            "Ремешок меняется без инструмента",
            "Ход точный, без заметного отставания",
        ),
        (12000, 420000),
        DARK,
    ),
    "jewelry": Kind(
        ("Кольцо", "Серьги", "Подвеска", "Браслет", "Цепочка", "Брошь"),
        ("серебро 925", "с гранатом", "ручной работы", "размеры 16–20", "с гравировкой"),
        ("серебра 925", "позолоченного серебра", "природного граната", "бирюзы"),
        (
            "Хорошо смотрится и днём, и на выход",
            "Не темнеет при повседневной носке",
            "Кладём в футляр — сразу можно дарить",
        ),
        (12000, 380000),
        BRIGHT,
    ),
    "books": Kind(
        ("Книга", "Альбом", "Блокнот", "Сборник рассказов", "Путеводитель", "Детская книга"),
        ("в твёрдом переплёте", "на армянском", "на русском", "с иллюстрациями", "288 страниц"),
        ("офсетной бумаги", "переработанного картона", "плотной мелованной бумаги"),
        (
            "Подойдёт для подарка и для собственной полки",
            "Иллюстрации напечатаны без пересвета",
            "Удобно читать в дороге",
        ),
        (2500, 26000),
        COOL,
    ),
    "handmade": Kind(
        ("Свеча", "Панно", "Керамическая фигурка", "Набор для вышивки", "Мыло ручной работы"),
        ("ручной работы", "из соевого воска", "в подарочной коробке", "в единственном экземпляре"),
        ("соевого воска", "глины ручной формовки", "льняного холста", "натуральных красителей"),
        (
            "Каждая вещь немного отличается — так и задумано",
            "Подойдёт как подарок, который не купишь в сети магазинов",
            "Делаем небольшими партиями",
        ),
        (2000, 48000),
        WARM,
    ),
    "sport": Kind(
        ("Коврик для йоги", "Гантели", "Скакалка", "Рюкзак для похода", "Термос", "Палки"),
        ("пара 5 кг", "6 мм", "объём 1 л", "35 л", "в чехле"),
        ("нескользящего каучука", "нержавеющей стали", "прочного нейлона", "алюминия"),
        (
            "Подойдёт для дома и для зала",
            "Не скользит даже на гладком полу",
            "Лёгкий, помещается в городской рюкзак",
        ),
        (3000, 85000),
        GREEN,
    ),
    "audio-video": Kind(
        ("Наушники", "Колонка портативная", "Саундбар", "Микрофон", "Проектор"),
        ("без проводов", "Bluetooth 5.3", "до 20 часов работы", "с шумоподавлением"),
        ("алюминия", "матового пластика", "тканевой обивки"),
        (
            "Звук чистый и на низкой громкости",
            "Подойдёт для дороги и для дома",
            "Заряда хватает на несколько дней",
        ),
        (8000, 320000),
        DARK,
    ),
    "computers": Kind(
        ("Ноутбук", "Монитор", "Клавиатура", "Мышь", "SSD-накопитель", "Док-станция"),
        ("15,6 дюйма", "16 ГБ", "на механических переключателях", "1 ТБ", "без провода", "с USB-C"),
        ("алюминиевого корпуса", "матового пластика", "закалённого стекла"),
        (
            "Тянет работу с документами и браузером на два десятка вкладок",
            "Подойдёт для учёбы и для офиса",
            "Не шумит под обычной нагрузкой",
        ),
        (25000, 950000),
        COOL,
    ),
    "smartphones": Kind(
        ("Смартфон", "Планшет", "Повербанк", "Чехол", "Защитное стекло", "Зарядное устройство"),
        ("128 ГБ", "20000 мА·ч", "с быстрой зарядкой", "из прозрачного силикона", "6,7 дюйма"),
        ("матового стекла", "силикона", "алюминия", "закалённого стекла"),
        (
            "Хватает на день активного использования",
            "Подойдёт как основной аппарат и как запасной",
            "Комплект полный, ничего докупать не нужно",
        ),
        (4000, 780000),
        COOL,
    ),
}

SHOP_WORDS = (
    ("Дом", "уюта"),
    ("Лавка", "мастера"),
    ("Гончарная", "мастерская"),
    ("Сад", "и дом"),
    ("Тепло", "гор"),
    ("Первый", "этаж"),
    ("Светлая", "комната"),
    ("Городские", "мелочи"),
    ("Ремесло", "и камень"),
    ("Хлопок", "и лён"),
    ("Тихая", "полка"),
    ("Солнечный", "склон"),
    ("Гранат", "и мёд"),
    ("Синяя", "дверь"),
    ("Мастерская", "у рынка"),
    ("Доброе", "утро"),
    ("Камень", "и нить"),
    ("Абрикос", "и соль"),
    ("Старый", "двор"),
    ("Ветка", "оливы"),
)

SHOP_ABOUT = (
    "Небольшая семейная мастерская: делаем сами, продаём сами.",
    "Работаем с 2019 года, половина покупателей приходит по совету знакомых.",
    "Привозим из регионов то, что не найти в сетевых магазинах.",
    "Держим цены ниже торговых центров: у нас нет аренды в галерее.",
    "Собираем заказы в день обращения, отправляем по всей Армении.",
    "Каждую вещь проверяем руками перед отправкой.",
)

REJECTIONS = (
    "Фотография не соответствует товару: пришлите снимок самого изделия.",
    "В описании нет состава и размеров — покупателю нечего сравнить.",
    "Цена указана без НДС, на витрине нужна итоговая.",
    "Название дублирует категорию, по нему товар не найти.",
)

COMPLAINTS = (
    "Товар не соответствует описанию, пришло другое.",
    "Продавец не отвечает на сообщения третий день.",
    "Цена на витрине и в переписке отличается вдвое.",
    "Фотография взята с другого сайта.",
    "Подозрительно дёшево для такого товара, похоже на обман.",
)

SUSPENSIONS = (
    "Жалобы покупателей на несоответствие товара описанию.",
    "Документы продавца не подтверждены в срок.",
)


def say(line: str = "") -> None:
    """The project forbids print; a script that reports to a person still has to talk."""
    sys.stdout.write(f"{line}\n")


def png(side: int, top: Colour, bottom: Colour) -> bytes:
    """A gradient square, written by hand — fake data needs no image library."""
    rows = bytearray()
    for y in range(side):
        weight = y / max(1, side - 1)
        colour = bytes(
            round(start + (end - start) * weight) for start, end in zip(top, bottom, strict=True)
        )
        rows.append(0)  # filter type of the scanline
        rows.extend(colour * side)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload))
        )

    header = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


def shade(colour: Colour, shift: int) -> Colour:
    return (
        max(0, min(255, colour[0] + shift)),
        max(0, min(255, colour[1] + shift)),
        max(0, min(255, colour[2] + shift)),
    )


def hex_colour(colour: Colour) -> str:
    return f"#{colour[0]:02x}{colour[1]:02x}{colour[2]:02x}"


@dataclass
class Upload:
    key: str
    data: bytes


class Uploader:
    """Object storage takes the bulk of the wall clock here, so it runs in threads.

    A boto3 client is not safe to share across threads, hence one per thread rather than
    one per upload — building it costs more than the PUT itself.
    """

    def __init__(self, settings: Settings, workers: int) -> None:
        self._settings = settings
        self._workers = workers
        self._local = threading.local()

    def _client(self) -> "S3Client":
        client: S3Client | None = getattr(self._local, "client", None)
        if client is None:
            client = build_s3_client(self._settings)
            self._local.client = client
        return client

    def _put(self, upload: Upload) -> None:
        self._client().put_object(
            Bucket=self._settings.s3_bucket,
            Key=upload.key,
            Body=upload.data,
            ContentType="image/png",
        )

    def send(self, uploads: Sequence[Upload]) -> None:
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            for _ in pool.map(self._put, uploads):
                pass


@dataclass
class Tally:
    shops: int = 0
    published: int = 0
    pending: int = 0
    rejected: int = 0
    hidden: int = 0
    archived: int = 0
    buyers: int = 0
    reports: int = 0
    images: int = 0


def product_name(rng: random.Random, kind: Kind) -> str:
    name = rng.choice(kind.items)
    if rng.random() < 0.55:
        name = f"{name} «{rng.choice(TITLES)}»"
    if rng.random() < 0.75:
        attr = rng.choice(kind.attrs)
        # a measurement is an aside and takes a comma ("Ваза, высота 30 см"); a phrase
        # describing the thing itself continues the name ("Ваза ручной работы")
        separator = ", " if any(char.isdigit() for char in attr) else " "
        name = f"{name}{separator}{attr}"
    return name


def product_description(rng: random.Random, kind: Kind) -> str:
    sentences = [
        f"Сделано из {rng.choice(kind.materials)}.",
        f"{rng.choice(kind.uses)}.",
    ]
    if rng.random() < 0.6:
        sentences.append(f"Цвет: {rng.choice(COLOURS)}.")
    sentences.append(rng.choice(CLOSERS))
    return " ".join(sentences)


def shop_name(rng: random.Random, index: int) -> tuple[str, str]:
    first, second = SHOP_WORDS[index % len(SHOP_WORDS)]
    suffix = "" if index < len(SHOP_WORDS) else f" {index // len(SHOP_WORDS) + 1}"
    display = f"{first} {second}{suffix}"
    subdomain = f"shop{index + 1:03d}"
    return display, subdomain


def moment(rng: random.Random, now: datetime) -> datetime:
    return now - timedelta(days=rng.randint(0, CATALOGUE_AGE_DAYS), minutes=rng.randint(0, 24 * 60))


def business_status(rng: random.Random) -> BusinessStatus:
    roll = rng.random()
    if roll < 0.88:
        return BusinessStatus.ACTIVE
    if roll < 0.95:
        return BusinessStatus.PENDING
    if roll < 0.98:
        return BusinessStatus.SUSPENDED
    return BusinessStatus.BLOCKED


def product_state(rng: random.Random) -> tuple[ModerationStatus, PublicationStatus, bool]:
    """Moderation status, publication status and whether the seller archived it."""
    roll = rng.random()
    if roll < 0.82:
        return ModerationStatus.APPROVED, PublicationStatus.PUBLISHED, False
    if roll < 0.90:
        return ModerationStatus.PENDING, PublicationStatus.DRAFT, False
    if roll < 0.94:
        return ModerationStatus.REJECTED, PublicationStatus.DRAFT, False
    if roll < 0.97:
        return ModerationStatus.APPROVED, PublicationStatus.HIDDEN, False
    return ModerationStatus.APPROVED, PublicationStatus.PUBLISHED, True


async def staff_id(session: AsyncSession) -> uuid.UUID | None:
    """Verdicts are signed by whoever moderates this stand, if anyone does yet."""
    found = await session.execute(
        select(User.id).where(User.role == UserRole.MODERATOR).order_by(User.created_at).limit(1)
    )
    return found.scalar_one_or_none()


async def reset(session: AsyncSession) -> int:
    """Drops the previous batch and only it: everything generated shares one email domain."""
    ours = User.email.like(f"%@{DOMAIN}")
    counted = await session.execute(select(func.count()).select_from(User).where(ours))
    await session.execute(delete(User).where(ours))
    await session.commit()
    return counted.scalar_one()


async def taken_subdomains(session: AsyncSession) -> set[str]:
    found = await session.execute(select(Store.subdomain))
    return set(found.scalars().all())


async def leaf_categories(session: AsyncSession) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
    """Leaf categories grouped by their parent section.

    A shop draws its range from one or two sections rather than from the whole tree: a
    storefront selling tablets next to jam is not something a search has to make sense of.
    """
    found = await session.execute(
        select(Category.id, Category.slug, Category.parent_id).where(
            Category.parent_id.is_not(None)
        )
    )
    sections: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
    for identifier, slug, parent_id in found.all():
        sections.setdefault(parent_id, []).append((identifier, slug))
    return sections


def contacts_for(rng: random.Random, business_id: uuid.UUID) -> list[SocialLink]:
    number = f"+3749{rng.randint(1000000, 9999999)}"
    links = [SocialLink(business_id=business_id, platform=ContactPlatform.PHONE, value=number)]
    if rng.random() < 0.7:
        links.append(
            SocialLink(business_id=business_id, platform=ContactPlatform.WHATSAPP, value=number)
        )
    if rng.random() < 0.45:
        links.append(
            SocialLink(
                business_id=business_id,
                platform=ContactPlatform.TELEGRAM,
                value=f"@shop{rng.randint(100, 999)}",
            )
        )
    return links


async def build(
    session: AsyncSession,
    settings: Settings,
    rng: random.Random,
    shops: int,
    products: int,
    buyers: int,
    reports: int,
    with_images: bool,
) -> Tally:
    tally = Tally()
    now = datetime.now(UTC)
    password_hash = hash_password(PASSWORD)  # hashed once: argon2 is slow on purpose
    moderator = await staff_id(session)
    sections = await leaf_categories(session)
    section_ids = list(sections)
    known = await taken_subdomains(session)
    uploads: list[Upload] = []
    published_ids: list[uuid.UUID] = []
    active_business_ids: list[uuid.UUID] = []

    per_shop = max(1, round(products / max(1, shops)))
    for index in range(shops):
        display, subdomain = shop_name(rng, index)
        if subdomain in known:
            continue
        known.add(subdomain)
        born = moment(rng, now)
        status = business_status(rng)

        user = User(
            email=f"{subdomain}@{DOMAIN}",
            password_hash=password_hash,
            role=UserRole.SELLER,
            created_at=born,
        )
        session.add(user)
        await session.flush()

        business = Business(
            owner_user_id=user.id,
            legal_name=f"ИП {display}",
            display_name=display,
            description=rng.choice(SHOP_ABOUT),
            status=status,
            created_at=born,
        )
        session.add(business)
        await session.flush()

        palette = rng.choice((WARM, COOL, GREEN, DARK, BRIGHT))
        store_status = {
            BusinessStatus.ACTIVE: StoreStatus.ACTIVE,
            BusinessStatus.PENDING: StoreStatus.DRAFT,
            BusinessStatus.SUSPENDED: StoreStatus.SUSPENDED,
            BusinessStatus.BLOCKED: StoreStatus.BLOCKED,
        }[status]
        store = Store(
            business_id=business.id,
            subdomain=subdomain,
            primary_color=hex_colour(palette[0]),
            secondary_color=hex_colour(palette[1]),
            status=store_status,
            created_at=born,
        )
        if with_images:
            logo_key = f"stores/{business.id}/logo/{uuid.uuid4().hex}.png"
            banner_key = f"stores/{business.id}/banner/{uuid.uuid4().hex}.png"
            uploads.append(Upload(logo_key, png(160, palette[0], palette[2])))
            uploads.append(Upload(banner_key, png(IMAGE_SIDE, palette[1], palette[0])))
            store.logo_url = public_url(settings, logo_key)
            store.banner_url = public_url(settings, banner_key)
            tally.images += 2
        session.add(store)
        session.add_all(contacts_for(rng, business.id))

        if status is not BusinessStatus.PENDING:
            decision = {
                BusinessStatus.ACTIVE: BusinessDecision.APPROVED,
                BusinessStatus.SUSPENDED: BusinessDecision.SUSPENDED,
                BusinessStatus.BLOCKED: BusinessDecision.BLOCKED,
            }[status]
            session.add(
                BusinessModerationReview(
                    business_id=business.id,
                    moderator_id=moderator,
                    decision=decision,
                    reason=(
                        None if decision is BusinessDecision.APPROVED else rng.choice(SUSPENSIONS)
                    ),
                    created_at=born + timedelta(hours=rng.randint(1, 48)),
                )
            )
        if status is BusinessStatus.ACTIVE:
            active_business_ids.append(business.id)
        tally.shops += 1

        # the range of this shop: one section, sometimes two neighbouring ones
        chosen = rng.sample(section_ids, k=1 if rng.random() < 0.6 else 2)
        shelf = [leaf for section in chosen for leaf in sections[section]]

        count = max(1, round(rng.uniform(0.5, 1.5) * per_shop))
        for _ in range(count):
            category_id, slug = rng.choice(shelf)
            kind = KINDS[slug]
            moderation, publication, archived = product_state(rng)
            listed = moment(rng, now)
            low, high = kind.price
            price = Decimal(rng.randrange(low, high, 100))
            product = Product(
                business_id=business.id,
                category_id=category_id,
                name=product_name(rng, kind),
                description=product_description(rng, kind),
                price=price,
                stock_quantity=rng.randint(0, 40),
                availability_status=(
                    ProductAvailability.IN_STOCK
                    if rng.random() < 0.9
                    else ProductAvailability.OUT_OF_STOCK
                ),
                moderation_status=moderation,
                publication_status=publication,
                archived_at=listed + timedelta(days=rng.randint(1, 30)) if archived else None,
                created_at=listed,
            )
            session.add(product)
            await session.flush()

            if moderation is not ModerationStatus.PENDING:
                decided = ModerationDecision.APPROVED
                reason = None
                if moderation is ModerationStatus.REJECTED:
                    decided, reason = ModerationDecision.REJECTED, rng.choice(REJECTIONS)
                elif publication is PublicationStatus.HIDDEN:
                    decided = ModerationDecision.HIDDEN
                session.add(
                    ModerationReview(
                        product_id=product.id,
                        moderator_id=moderator,
                        decision=decided,
                        reason=reason,
                        created_at=listed + timedelta(hours=rng.randint(1, 72)),
                    )
                )

            if with_images and rng.random() < 0.92:
                top = shade(rng.choice(kind.palette), rng.randint(-25, 25))
                bottom = shade(rng.choice(kind.palette), rng.randint(-25, 25))
                key = f"products/{business.id}/{product.id}/{uuid.uuid4().hex}.png"
                uploads.append(Upload(key, png(IMAGE_SIDE, top, bottom)))
                session.add(
                    ProductImage(
                        product_id=product.id,
                        image_url=public_url(settings, key),
                        sort_order=0,
                        alt_text=product.name,
                    )
                )
                tally.images += 1

            if archived:
                tally.archived += 1
            elif moderation is ModerationStatus.PENDING:
                tally.pending += 1
            elif moderation is ModerationStatus.REJECTED:
                tally.rejected += 1
            elif publication is PublicationStatus.HIDDEN:
                tally.hidden += 1
            else:
                tally.published += 1
                if status is BusinessStatus.ACTIVE:
                    published_ids.append(product.id)

        await session.commit()

    buyer_ids: list[uuid.UUID] = []
    for number in range(buyers):
        buyer = User(
            email=f"buyer{number + 1:03d}@{DOMAIN}",
            password_hash=password_hash,
            role=UserRole.BUYER,
            created_at=moment(rng, now),
        )
        session.add(buyer)
        await session.flush()
        buyer_ids.append(buyer.id)
        tally.buyers += 1
    await session.commit()

    for _ in range(reports):
        on_product = rng.random() < 0.75 and published_ids
        session.add(
            Report(
                reporter_user_id=(
                    rng.choice(buyer_ids) if buyer_ids and rng.random() < 0.6 else None
                ),
                product_id=rng.choice(published_ids) if on_product else None,
                business_id=None if on_product else rng.choice(active_business_ids),
                reason=rng.choice(COMPLAINTS),
                status=ReportStatus.OPEN,
            )
        )
        tally.reports += 1
    await session.commit()

    if uploads:
        say(f"Загружаю {len(uploads)} изображений в хранилище…")
        Uploader(settings, workers=16).send(uploads)

    return tally


async def main(arguments: argparse.Namespace) -> None:
    settings = get_settings()
    # S311: a seeded generator is the point here — same seed, same catalogue, nothing secret
    rng = random.Random(arguments.seed)  # noqa: S311
    engine = create_async_engine(str(settings.database_url))
    try:
        async with AsyncSession(engine) as session:
            if arguments.reset:
                removed = await reset(session)
                say(f"Прежняя партия удалена: {removed} аккаунтов вместе со всем, что за ними.")
            tally = await build(
                session,
                settings,
                rng,
                shops=arguments.shops,
                products=arguments.products,
                buyers=arguments.buyers,
                reports=arguments.reports,
                with_images=not arguments.no_images,
            )
    finally:
        await engine.dispose()

    total = tally.published + tally.pending + tally.rejected + tally.hidden + tally.archived
    say()
    say("Готово.")
    say(f"  магазинов: {tally.shops}")
    say(f"  товаров: {total}")
    say(f"    опубликовано: {tally.published}")
    say(f"    на проверке: {tally.pending}, отклонено: {tally.rejected}")
    say(f"    скрыто модератором: {tally.hidden}, архивировано продавцом: {tally.archived}")
    say(f"  покупателей: {tally.buyers}, открытых жалоб: {tally.reports}")
    say(f"  изображений: {tally.images}")
    say()
    say(f"Вход в любой из магазинов: shop001@{DOMAIN} … пароль {PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shops", type=int, default=60)
    parser.add_argument("--products", type=int, default=2000, help="примерное общее число")
    parser.add_argument("--buyers", type=int, default=150)
    parser.add_argument("--reports", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260923, help="одинаковый seed — те же данные")
    parser.add_argument("--reset", action="store_true", help=f"сначала удалить всё с @{DOMAIN}")
    parser.add_argument("--no-images", action="store_true", help="не трогать объектное хранилище")
    asyncio.run(main(parser.parse_args()))
