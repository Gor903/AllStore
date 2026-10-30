# Architecture Decision Records

Один файл на решение: `NNNN-краткое-название.md`, нумерация сквозная.
Структура записи: Контекст → Решение → Альтернативы → Последствия → Статус
(`proposed` / `accepted` / `superseded by NNNN`). Принятые записи не переписываются:
изменение решения — это новый ADR со ссылкой на предыдущий.

Решения, которые раздел 11 плана сборки требует зафиксировать до начала соответствующего этапа:

| # | Решение | Нужно к этапу | Статус |
| - | ------- | ------------- | ------ |
| 1 | [Авторизация](0001-authentication.md) | 2 | superseded by 18 |
| 2 | [Хранение паролей](0002-password-storage.md) | 2 | accepted, параметры уточнены [ADR 25](0025-argon2-cost-measured.md) |
| 3 | Стратегия кэширования публичных страниц | 6 | открыт |
| 4 | [Типы frontend из OpenAPI](0004-api-types-generation.md) | 2 | accepted |
| 5 | Провайдер email-уведомлений | 8 | открыт, временно обойдён [ADR 19](0019-transactional-mail.md) |
| 6 | Стратегия резервного копирования PostgreSQL | 1–9 (до продакшена) | открыт |
| 7 | [Порог покрытия тестами](0007-test-coverage-threshold.md) | 2 | accepted |

Решения, принятые по ходу работы и не привязанные к разделу 11:

| # | Решение | Этап | Статус |
| - | ------- | ---- | ------ |
| 13 | [Семантический поиск](0013-semantic-search.md) | 16 | accepted |
| 15 | [Иерархия ролей и модерация](0015-roles-and-moderation.md) | 18 | accepted |
| 16 | [Админка: жизненный цикл, видимость, состояние](0016-admin-panel-and-visibility.md) | 19 | accepted |
| 17 | [Модератора заводит администратор, приглашений нет](0017-moderators-appointed-directly.md) | 19 | accepted |
| 18 | [Серверные сессии и привязка к устройству](0018-server-side-sessions.md) | рефактор auth | accepted |
| 19 | [Транзакционная почта: временно личный Gmail](0019-transactional-mail.md) | рефактор auth | accepted |
| 20 | [Вход через Google: идентичность по sub](0020-google-sign-in.md) | рефактор auth | superseded by 26 |
| 21 | [Журнал безопасности и уведомления](0021-security-journal-and-notices.md) | рефактор auth | accepted |
| 22 | [Фоновая работа: Celery, почта через очередь](0022-background-work-on-celery.md) | рефактор auth | accepted |
| 23 | [Второй фактор для staff: TOTP](0023-staff-second-factor.md) | рефактор auth | accepted |
| 24 | [Сигналы риска: заложены и выключены](0024-risk-signals.md) | рефактор auth | accepted |
| 25 | [argon2: 64 MiB, взятые из замера](0025-argon2-cost-measured.md) | рефактор auth | accepted, уточняет 2 |
| 26 | [Вход через Google убран](0026-google-sign-in-removed.md) | рефактор auth | accepted, отменяет 20 |
| 27 | [Письмо заведённому staff-аккаунту](0027-staff-account-letter.md) | рефактор auth | accepted, дополняет 17 |
