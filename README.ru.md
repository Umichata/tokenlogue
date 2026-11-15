[English](README.md#english) · [Русский](README.ru.md#russian)

<a id="russian"></a>
<a id="lang-ru"></a>

# Tokenlogue

<p align="center"><img src="docs/assets/tokenlogue-logo-transparent.svg" alt="Логотип Tokenlogue" width="104"></p>

**Чаты OpenRouter и VSEGPT для Linux и Android.** Храните разговоры и черновики вместе, выбирайте модель для каждого чата и следите за токенами и расходами.

[**Главная**](https://github.com/Umichata/tokenlogue/tree/main) · [Android](https://github.com/Umichata/tokenlogue/tree/android) · [Linux](https://github.com/Umichata/tokenlogue/tree/linux)

[Возможности](#ru-features) · [Интерфейс](#ru-screenshots) · [Установка](#ru-start) · [Руководство](docs/user-guide.ru.md) · [Карта документации](docs/README.ru.md)

> **0.1.1 доступна локально.** Руководство описывает текущие исходники и локальные сборки. [Опубликованный 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) — прежний выпуск. По его ссылкам нельзя скачать 0.1.1.


<a id="ru-features"></a>
## Возможности

- Храните ключи OpenRouter и VSEGPT отдельно в защищённом хранилище.
- Проверяйте провайдера и маску общего ключа в **⋮** и [явно меняйте провайдера выбранного чата](docs/user-guide.ru.md#ru-chat-connection).
- Переходите между **Главной**, **Провайдерами**, **Токенами** и **Расходами**, сохраняя текущий чат и черновик.
- Выбирайте **Все · OpenRouter · VSEGPT** для просмотра одного или двух сервисов. Фильтр просмотра не меняет провайдера чата.
- Смотрите местную статистику токенов и дневных расходов по сервису и модели. USD и RUB остаются раздельными.
- Проверяйте приблизительную стоимость и предупреждения бюджета перед платной отправкой.
- Используйте русский или английский язык, вход по PIN и шифрование сохранённых полей переписки.

<a id="ru-screenshots"></a>
## Интерфейс

| Linux | Эмулятор Android |
| --- | --- |
| <a href="docs/assets/screenshots/v011-linux-home-ru.png"><img src="docs/assets/screenshots/v011-linux-home-ru.png" alt="Главная с перепиской и сохранённым черновиком в Linux" width="560"></a> | <a href="docs/assets/screenshots/v011-android-home-ru.png"><img src="docs/assets/screenshots/v011-android-home-ru.png" alt="Главная с перепиской и сохранённым черновиком в эмуляторе Android" width="300"></a> |

*Демонстрационные данные. Кадры Android сняты в эмуляторе.*

<a id="ru-start"></a>
## Установка и обновление

| Платформа | Текущая локальная версия | Опубликованный пакет |
| --- | --- | --- |
| Android ARM64 | APK 0.1.1, Android 7.0 / API 24 или новее | [APK 0.1.0](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) · [Установка](docs/android.ru.md) |
| Linux x86_64 | Настольный bundle 0.1.1 | [AppImage 0.1.0](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) · [Установка](docs/linux-appimage.ru.md) |

На странице [опубликованного выпуска](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) есть [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS). Сверьте пакет до установки. AppImage не подписана. Для готового приложения не нужны Python, Flutter и архивы исходников.

Совместимый APK с прежней подписью устанавливайте поверх приложения с сохранением данных. В Linux закройте старые копии перед запуском замены от той же учётной записи ОС.

### Первое подключение

1. Введите поддерживаемый ключ и нажмите **Проверить ключ**. Если бесплатная проверка VSEGPT недоступна, можно явно сохранить его непроверенным.
2. Выберите и повторите PIN приложения. Сохраните предложенные для платформы материалы восстановления.
3. Через **+** создайте чат, выберите модель и лимиты, затем напишите сообщение.

Подробнее о [чатах](docs/user-guide.ru.md), [настройках провайдеров](docs/providers.ru.md) и [статистике токенов и расходов](docs/analytics.ru.md).

## Что означают суммы

Баланс сервиса, остаток лимита ключа OpenRouter и бюджет чата — разные значения. Для VSEGPT отдельный лимит ключа не поддерживается. Неизвестные суммы остаются недоступными. Местные оценки токенов и стоимости приблизительны.

PIN и шифрование защищают отдельные локальные поля. Они не шифруют всё устройство. При отправке нужный контекст получает сервис, закреплённый за чатом, и его поставщик модели. В разделе [защиты и восстановления](docs/security.ru.md) описаны требования и последствия удаления профиля.

## Исходники и лицензии

Tokenlogue распространяется по [лицензии MIT](LICENSE). [Исходные материалы](docs/source-materials.ru.md) и [сторонние уведомления](THIRD_PARTY_NOTICES.ru.md) описывают компоненты и ограничения подтверждённого происхождения бинарников. См. [изменения 0.1.1](CHANGELOG.ru.md).
