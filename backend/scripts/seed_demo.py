"""Fills a running local stack with demo data: buyers, sellers, shops, products, verdicts.

    docker compose up -d
    cd backend && uv run python -m scripts.seed_demo

Everything the public API can do is done through the public API, exactly as a person
would. Two things have no endpoint yet and are written straight to the database: accounts
with the moderator and admin roles (there is no self-registration for them) and the shop
description (registration does not accept one).
"""

import argparse
import asyncio
import os
import struct
import sys
import zlib
from dataclasses import dataclass, field

import httpx

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

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User, UserRole  # noqa: E402

# one password for every demo account, printed at the end — this stack is local only
PASSWORD = "demo-password-1"  # noqa: S105
DEFAULT_GATEWAY = "http://localhost:8081"

Colour = tuple[int, int, int]


@dataclass(frozen=True)
class ProductSpec:
    name: str
    category: str
    price: str
    description: str
    top: Colour
    bottom: Colour
    stock: int = 5
    # published | pending | rejected | hidden | archived — the shelf the product ends on
    fate: str = "published"


@dataclass(frozen=True)
class ShopSpec:
    display_name: str
    legal_name: str
    subdomain: str
    description: str
    products: tuple[ProductSpec, ...]
    admitted: bool = True


CLAY: Colour = (196, 128, 92)
SAND: Colour = (238, 214, 186)
SLATE: Colour = (52, 62, 78)
STEEL: Colour = (142, 158, 178)
BERRY: Colour = (156, 46, 72)
CREAM: Colour = (246, 232, 214)
MOSS: Colour = (92, 122, 84)
LINEN: Colour = (222, 224, 210)
SILVER: Colour = (176, 180, 190)
NIGHT: Colour = (32, 36, 48)

SHOPS: tuple[ShopSpec, ...] = (
    ShopSpec(
        display_name="Гончарная лавка",
        legal_name='ИП "Саркисян А."',
        subdomain="keramika",
        description="Керамика ручной работы из Гюмри: посуда, вазы, подарочные наборы.",
        products=(
            ProductSpec(
                name="Кружка керамическая «Арарат»",
                category="tableware",
                price="4500.00",
                description=(
                    "Ручная лепка, объём 350 мл, обжиг при 1200 °C.\nМожно мыть в посудомойке."
                ),
                top=CLAY,
                bottom=SAND,
                stock=12,
            ),
            ProductSpec(
                name="Тарелка глубокая, набор 4 шт.",
                category="tableware",
                price="16000.00",
                description="Набор из четырёх тарелок, диаметр 22 см. Каждая расписана вручную.",
                top=SAND,
                bottom=CLAY,
                stock=4,
            ),
            ProductSpec(
                name="Ваза «Гюмри», высота 30 см",
                category="handmade",
                price="12500.00",
                description="Единственный экземпляр, подпись мастера на дне.",
                top=CLAY,
                bottom=MOSS,
                stock=1,
            ),
            ProductSpec(
                name="Чайник заварочный, 800 мл",
                category="tableware",
                price="9800.00",
                description="С глиняным фильтром, держит температуру около часа.",
                top=MOSS,
                bottom=SAND,
                stock=3,
                fate="hidden",
            ),
        ),
    ),
    ShopSpec(
        display_name="Техно Ереван",
        legal_name='ООО "Техно Ереван"',
        subdomain="tehno",
        description="Смартфоны, ноутбуки и аудио с официальной гарантией. Самовывоз в центре.",
        products=(
            ProductSpec(
                name="Смартфон Nova 12, 256 ГБ",
                category="smartphones",
                price="189000.00",
                description="Экран 6.7″ AMOLED, батарея 5000 мА·ч, гарантия 12 месяцев.",
                top=SLATE,
                bottom=STEEL,
                stock=7,
            ),
            ProductSpec(
                name="Ноутбук Vega Air 14",
                category="computers",
                price="465000.00",
                description="14″, 16 ГБ памяти, накопитель 512 ГБ. Русская и армянская раскладка.",
                top=STEEL,
                bottom=SLATE,
                stock=2,
            ),
            ProductSpec(
                name="Наушники Echo Pods",
                category="audio-video",
                price="34900.00",
                description="Активное шумоподавление, до 30 часов с кейсом.",
                top=NIGHT,
                bottom=STEEL,
                stock=15,
            ),
            ProductSpec(
                name="Powerbank 20000 мА·ч",
                category="smartphones",
                price="12900.00",
                description="Два выхода USB-C, быстрая зарядка 30 Вт.",
                top=SLATE,
                bottom=NIGHT,
                stock=20,
            ),
            ProductSpec(
                name="Смарт-часы Chrono S",
                category="watches",
                price="58000.00",
                description="Пульс, кислород, GPS. Ремешок меняется без инструмента.",
                top=NIGHT,
                bottom=SILVER,
                stock=6,
                fate="pending",
            ),
        ),
    ),
    ShopSpec(
        display_name="Армянские сладости",
        legal_name='ИП "Мкртчян Л."',
        subdomain="anush",
        description="Сухофрукты, пахлава и варенье по домашним рецептам. Доставка по Еревану.",
        products=(
            ProductSpec(
                name="Пахлава медовая, 500 г",
                category="sweets",
                price="3200.00",
                description="Грецкий орех, мёд, тонкое тесто. Без консервантов, срок 14 дней.",
                top=BERRY,
                bottom=CREAM,
                stock=30,
            ),
            ProductSpec(
                name="Суджух ореховый, 3 шт.",
                category="sweets",
                price="2800.00",
                description="Виноградный сок и грецкий орех, больше ничего.",
                top=CREAM,
                bottom=BERRY,
                stock=25,
            ),
            ProductSpec(
                name="Варенье из грецкого ореха, 450 г",
                category="groceries",
                price="4100.00",
                description="Зелёный орех молочной спелости, варится шесть часов.",
                top=MOSS,
                bottom=CREAM,
                stock=10,
            ),
            ProductSpec(
                name="Гранатовый сок, 1 л",
                category="beverages",
                price="1900.00",
                description="Прямой отжим, без сахара и воды.",
                top=BERRY,
                bottom=NIGHT,
                stock=40,
            ),
            ProductSpec(
                name="Набор «Подарок из Армении»",
                category="sweets",
                price="8900.00",
                description="Пахлава, суджух, сухофрукты и травяной чай в коробке.",
                top=CREAM,
                bottom=CLAY,
                stock=8,
                fate="archived",
            ),
        ),
    ),
    ShopSpec(
        display_name="Ковры и текстиль",
        legal_name='ИП "Ованнисян Т."',
        subdomain="karpet",
        description="Ковры ручной работы, пледы и скатерти. Своё производство в Ванадзоре.",
        products=(
            ProductSpec(
                name="Ковёр шерстяной 150×200",
                category="home-textiles",
                price="240000.00",
                description="Ручное ткачество, натуральная шерсть, традиционный орнамент.",
                top=BERRY,
                bottom=SAND,
                stock=2,
            ),
            ProductSpec(
                name="Плед хлопковый 130×170",
                category="home-textiles",
                price="18500.00",
                description="Плотное плетение, не электризуется, стирка при 40 °C.",
                top=LINEN,
                bottom=MOSS,
                stock=14,
            ),
            ProductSpec(
                name="Скатерть льняная 140×240",
                category="home-textiles",
                price="22000.00",
                description="Лён без примесей, край обработан вручную.",
                top=LINEN,
                bottom=SAND,
                stock=6,
            ),
            ProductSpec(
                name="Табурет деревянный с плетением",
                category="furniture",
                price="27500.00",
                description="Бук и джут, выдерживает до 120 кг.",
                top=SAND,
                bottom=SLATE,
                stock=5,
                fate="rejected",
            ),
        ),
    ),
    ShopSpec(
        display_name="Мастерская серебра",
        legal_name='ИП "Петросян Г."',
        subdomain="arciv",
        description="Серебро 925 пробы ручной работы. Заявка ещё ждёт проверки модератора.",
        admitted=False,
        products=(
            ProductSpec(
                name="Кольцо «Урарту», серебро 925",
                category="jewelry",
                price="34000.00",
                description="Ручная гравировка, размеры 16–20.",
                top=SILVER,
                bottom=NIGHT,
                stock=4,
            ),
            ProductSpec(
                name="Серьги «Гранат»",
                category="jewelry",
                price="41000.00",
                description="Серебро с природным гранатом.",
                top=BERRY,
                bottom=SILVER,
                stock=3,
            ),
        ),
    ),
)

BUYERS: tuple[tuple[str, str], ...] = (
    ("anna@demo.allstore.am", "Анна"),
    ("karen@demo.allstore.am", "Карен"),
    ("marine@demo.allstore.am", "Марине"),
)

REJECTION = "Фотография не соответствует товару: пришлите снимок самого изделия, а не каталога."


def png(width: int, height: int, top: Colour, bottom: Colour) -> bytes:
    """A gradient of the given size, written by hand — a demo needs no image library."""
    rows = bytearray()
    for y in range(height):
        weight = y / max(1, height - 1)
        colour = bytes(
            round(start + (end - start) * weight) for start, end in zip(top, bottom, strict=True)
        )
        rows.append(0)  # filter type of the scanline
        rows.extend(colour * width)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


@dataclass
class Result:
    shops: list[tuple[ShopSpec, str]] = field(default_factory=list)
    published: int = 0
    pending: int = 0
    rejected: int = 0
    hidden: int = 0
    archived: int = 0


def say(line: str = "") -> None:
    """The project forbids print; a script that reports to a person still has to talk."""
    sys.stdout.write(f"{line}\n")


def csrf(client: httpx.AsyncClient) -> dict[str, str]:
    token = client.cookies.get("allstore_csrf")
    return {} if token is None else {"X-CSRF-Token": token}


async def expect(response: httpx.Response, *, code: int, what: str) -> httpx.Response:
    if response.status_code != code:
        raise SystemExit(
            f"{what}: ожидался {code}, пришёл {response.status_code} — {response.text}"
        )
    return response


async def seed_accounts(session: AsyncSession) -> None:
    """The two roles nobody can register into, written where they can be written at all."""
    for email, role in (
        ("moderator@demo.allstore.am", UserRole.MODERATOR),
        ("admin@demo.allstore.am", UserRole.ADMIN),
    ):
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(User(email=email, password_hash=hash_password(PASSWORD), role=role))
    await session.commit()


async def describe_shops(session: AsyncSession, shops: list[tuple[ShopSpec, str]]) -> None:
    """Registration takes no description and nothing else sets one — hence the direct write."""
    for spec, business_id in shops:
        await session.execute(
            text("UPDATE businesses SET description = :description WHERE id = :id"),
            {"description": spec.description, "id": business_id},
        )
    await session.commit()


async def category_ids(session: AsyncSession) -> dict[str, str]:
    rows = await session.execute(text("SELECT slug, id::text FROM categories"))
    return dict(rows.all())  # type: ignore[arg-type]


async def open_shop(
    base_url: str, spec: ShopSpec, slugs: dict[str, str], result: Result
) -> tuple[str, list[tuple[ProductSpec, str]]]:
    """Registers the seller, opens the storefront and fills it. Returns ids for moderation."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        registered = await expect(
            await client.post(
                "/api/v1/auth/register/seller",
                json={
                    "email": f"{spec.subdomain}@demo.allstore.am",
                    "password": PASSWORD,
                    "legal_name": spec.legal_name,
                    "display_name": spec.display_name,
                },
            ),
            code=201,
            what=f"регистрация {spec.display_name}",
        )
        business_id = str(registered.json()["business"]["id"])
        await expect(
            await client.post(
                "/api/v1/stores", json={"subdomain": spec.subdomain}, headers=csrf(client)
            ),
            code=201,
            what=f"витрина {spec.subdomain}",
        )

        products: list[tuple[ProductSpec, str]] = []
        for product in spec.products:
            created = await expect(
                await client.post(
                    "/api/v1/products",
                    json={
                        "category_id": slugs[product.category],
                        "name": product.name,
                        "description": product.description,
                        "price": product.price,
                        "stock_quantity": product.stock,
                    },
                    headers=csrf(client),
                ),
                code=201,
                what=f"товар {product.name}",
            )
            product_id = str(created.json()["id"])
            await expect(
                await client.post(
                    f"/api/v1/products/{product_id}/images",
                    files={
                        "file": (
                            f"{product_id}.png",
                            png(640, 640, product.top, product.bottom),
                            "image/png",
                        )
                    },
                    data={"alt_text": product.name},
                    headers=csrf(client),
                ),
                code=201,
                what=f"фото {product.name}",
            )
            products.append((product, product_id))

        if spec.admitted:
            result.shops.append((spec, business_id))
        return business_id, products


async def moderate(
    base_url: str,
    shops: list[tuple[ShopSpec, str, list[tuple[ProductSpec, str]]]],
    result: Result,
) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        await expect(
            await client.post(
                "/api/v1/auth/login",
                json={"email": "moderator@demo.allstore.am", "password": PASSWORD},
            ),
            code=200,
            what="вход модератора",
        )
        for spec, business_id, products in shops:
            if not spec.admitted:
                result.pending += len(products)
                continue
            await expect(
                await client.post(
                    f"/api/v1/moderation/businesses/{business_id}/approve", headers=csrf(client)
                ),
                code=200,
                what=f"допуск {spec.display_name}",
            )
            for product, product_id in products:
                await decide(client, product, product_id, result)


async def decide(
    client: httpx.AsyncClient, product: ProductSpec, product_id: str, result: Result
) -> None:
    moderation = f"/api/v1/moderation/products/{product_id}"
    if product.fate == "pending":
        result.pending += 1
        return
    if product.fate == "rejected":
        await expect(
            await client.post(
                f"{moderation}/reject", json={"reason": REJECTION}, headers=csrf(client)
            ),
            code=200,
            what=f"отказ по {product.name}",
        )
        result.rejected += 1
        return

    await expect(
        await client.post(f"{moderation}/approve", headers=csrf(client)),
        code=200,
        what=f"одобрение {product.name}",
    )
    if product.fate == "hidden":
        await expect(
            await client.post(f"{moderation}/hide", headers=csrf(client)),
            code=200,
            what=f"скрытие {product.name}",
        )
        result.hidden += 1
    elif product.fate == "archived":
        result.archived += 1
    else:
        result.published += 1


async def archive(base_url: str, spec: ShopSpec, products: list[tuple[ProductSpec, str]]) -> None:
    """Archiving belongs to the seller, so it happens from the seller's own session."""
    doomed = [pid for product, pid in products if product.fate == "archived"]
    if not doomed:
        return
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        await expect(
            await client.post(
                "/api/v1/auth/login",
                json={"email": f"{spec.subdomain}@demo.allstore.am", "password": PASSWORD},
            ),
            code=200,
            what=f"вход {spec.display_name}",
        )
        for product_id in doomed:
            await expect(
                await client.delete(f"/api/v1/products/{product_id}", headers=csrf(client)),
                code=204,
                what="архивация",
            )


async def register_buyers(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        for email, name in BUYERS:
            await expect(
                await client.post(
                    "/api/v1/auth/register/buyer", json={"email": email, "password": PASSWORD}
                ),
                code=201,
                what=f"покупатель {name}",
            )


async def wipe(session: AsyncSession) -> None:
    await session.execute(text("TRUNCATE users CASCADE"))
    await session.commit()


async def main(base_url: str, should_wipe: bool) -> None:
    engine = create_async_engine(str(get_settings().database_url))
    result = Result()
    try:
        async with AsyncSession(engine) as session:
            if should_wipe:
                await wipe(session)
                say("Прежние данные удалены (категории остались).")
            await seed_accounts(session)
            slugs = await category_ids(session)

        opened: list[tuple[ShopSpec, str, list[tuple[ProductSpec, str]]]] = []
        for spec in SHOPS:
            business_id, products = await open_shop(base_url, spec, slugs, result)
            opened.append((spec, business_id, products))
            say(f"Магазин {spec.display_name}: {len(products)} товаров заведено.")

        await moderate(base_url, opened, result)
        for spec, _business_id, products in opened:
            await archive(base_url, spec, products)
        await register_buyers(base_url)

        async with AsyncSession(engine) as session:
            await describe_shops(session, result.shops)
    finally:
        await engine.dispose()

    report(base_url, result)


def report(base_url: str, result: Result) -> None:
    say()
    say("Готово.")
    say(f"  магазинов в эфире: {len(result.shops)}, один ждёт проверки")
    say(f"  товаров опубликовано: {result.published}")
    say(f"  на проверке: {result.pending}, отклонён: {result.rejected}")
    say(f"  скрыт модератором: {result.hidden}, архивирован продавцом: {result.archived}")
    say()
    say(f"Каталог:  {base_url}/catalog")
    say(f"Магазины: {base_url}/stores")
    for spec, _ in result.shops:
        say(f"  {spec.display_name}: {base_url}/s/{spec.subdomain}")
    say()
    say(f"Пароль у всех демо-аккаунтов: {PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("DEMO_BASE_URL", DEFAULT_GATEWAY))
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="удалить прежних пользователей и всё, что за ними, перед наполнением",
    )
    arguments = parser.parse_args()
    asyncio.run(main(arguments.base_url, arguments.wipe))
