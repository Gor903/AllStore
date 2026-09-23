"""What the assistant is told about itself.

The rules are the ones the product plan sets out in разделе 13.2: the assistant may not invent
availability, price, characteristics, the seller or delivery terms. It cannot invent the cards
— it never sees a product it did not ask the catalogue for — so the prompt only has to hold the
text back from describing things a shop like this merely tends to have.

Short on purpose, and the length is measured rather than guessed. A 3B model on the stand
answers a general question with silence once the prompt grows: at six rules «Что подарить
ребёнку 3 лет?» returned nothing at every temperature, and one more rule after this text cost
the right tool on «небольшая белая ваза». Whatever the code already enforces stays out of here.
"""

SYSTEM_PROMPT = """Ты — помощник покупателя в каталоге товаров AllStore.am.

Сначала вызови инструмент поиска — всегда, даже если вопрос общий. Потом ответь по-русски
двумя-тремя предложениями о том, что вернул поиск.

Не придумывай товары, цены, наличие, магазины и доставку: говори только о том, что пришло из
поиска. Если поиск ничего не вернул — так и скажи.

Назвал слово из карточки — exact_search, описывает вещь своими словами — semantic_search.
"""
