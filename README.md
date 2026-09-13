# Tokenlogue

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

[English](#lang-en) | [Русский](#lang-ru)

<img src="docs/assets/tokenlogue-icon-512.png" alt="Tokenlogue application icon" width="128">

Tokenlogue is an OpenRouter chat client with local conversation history and
configurable token and spending limits. The application interface is currently
in Russian. These links navigate between the two documentation languages.

### Get the Linux preview

The available preview is `Tokenlogue-0.1.0-1472c00-x86_64.AppImage`.
Follow the [Linux guide](docs/linux-appimage.md#lang-en) to download it from
GitHub Actions, check its SHA-256 and run it. It needs an x86-64-v2 compatible
processor, system GTK3, graphics support and a working Secret Service.
You do not need to install Python, uv or Flutter SDK to run the AppImage.

This is an unsigned preview distributed as an Actions artifact, with limited
retention and no automatic updates. No public Release download is established
for this file. Windows and Android are target platforms without confirmed
ready-to-use packages. DEB and RPM packages are also unavailable.

### Everyday use

- Enter your OpenRouter API key, save the generated four-digit PIN and use
  that PIN to unlock the application later.
- Create separate chats with a free or paid model and their own limits.
- Keep conversation history locally and resume a separate saved draft in
  each chat after switching chats or restarting.
- Review used, reserved and remaining tokens and costs before sending.
- Confirm paid requests and increases to a chat's spending limit.

The compact header keeps the chat title, new-chat button `+`, lock button
and menu `⋮` visible. Open `⋮` on the right for key status, mode, model, budget,
limits, renaming and deletion. In a narrow window, open the chat list with
the menu button on the left. The editor stays at the bottom.

The [user guide](docs/user-guide.md#lang-en) explains setup, keyboard controls,
drafts, limits and requests with an unknown outcome.

### Your data and OpenRouter

History and drafts are stored in a local SQLite database without additional
content encryption. The PIN restricts access through the interface and is
not stored as plain text. The API key is stored separately through the
platform's SecureStorage. Protect your operating-system account and backups.

Sending a message sends its text and conversation context to OpenRouter for
processing by the selected model provider. Unsent drafts are kept locally
and do not consume the chat budget. OpenRouter is a separate service with its
own account, network access and usage conditions. Tokenlogue is not affiliated
with OpenRouter. Read about [storage and reset](docs/user-guide.md#en-data).

### Sources and licenses

Tokenlogue's own code is available under the [MIT License](LICENSE).
The [third-party overview](THIRD_PARTY_NOTICES.md#lang-en) explains the main
dependencies and links to the notices included in the AppImage.

[Source materials](docs/source-materials.md#lang-en) include the application
source and a separate runtime bundle. The guide explains which materials are
available and what is still missing for an offline rebuild of the application.

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-ru"></a>

## Русский

[English](#lang-en) | [Русский](#lang-ru)

<img src="docs/assets/tokenlogue-icon-512.png" alt="Значок приложения Tokenlogue" width="128">

Tokenlogue - клиент OpenRouter с локальной историей диалогов и настраиваемыми
лимитами токенов и расходов. Интерфейс приложения сейчас на русском языке.
Ссылки переключают читателя между языковыми разделами документации.

### Получение предварительной сборки для Linux

Доступная предварительная сборка - `Tokenlogue-0.1.0-1472c00-x86_64.AppImage`.
В [руководстве для Linux](docs/linux-appimage.md#lang-ru) описаны скачивание
из GitHub Actions, проверка SHA-256 и запуск. Нужны процессор с поддержкой
x86-64-v2, системная GTK3, работающая графическая подсистема и Secret Service.
Отдельно устанавливать Python, uv или Flutter SDK для запуска AppImage не нужно.

Это неподписанная предварительная сборка в виде артефакта Actions с
ограниченным сроком хранения и без автоматического обновления. Публичная
загрузка через Release для этого файла не подтверждена. Windows и Android
остаются целевыми платформами без подтверждённых готовых пакетов.
Пакеты DEB и RPM также недоступны.

### Повседневная работа

- Введите API-ключ OpenRouter, сохраните созданный четырёхзначный PIN и
  используйте его для следующих входов.
- Создавайте отдельные чаты с бесплатной или платной моделью и своими лимитами.
- Храните историю локально и возвращайтесь к отдельному черновику каждого
  чата после переключения или перезапуска.
- Проверяйте использованные, зарезервированные и оставшиеся токены и средства
  перед отправкой.
- Подтверждайте платные запросы и увеличение денежного лимита чата.

В компактной шапке остаются название чата, кнопка нового чата `+`, блокировка
и меню `⋮`. Откройте `⋮` справа, чтобы увидеть состояние ключа, режим, модель,
бюджет и лимиты, переименовать или удалить чат. В узком окне список чатов
открывается кнопкой меню слева. Редактор остаётся внизу.

[Руководство пользователя](docs/user-guide.md#lang-ru) описывает настройку,
клавиатурное управление, черновики, лимиты и запросы с неизвестным результатом.

### Ваши данные и OpenRouter

История и черновики находятся в локальной SQLite-базе без дополнительного
шифрования содержимого. PIN ограничивает вход через интерфейс и не хранится
открытым текстом. API-ключ сохраняется отдельно через платформенное
SecureStorage. Защищайте свою учётную запись ОС и резервные копии.

При отправке сообщения его текст и контекст диалога передаются в OpenRouter
для обработки выбранным поставщиком модели. Неотправленные черновики остаются
локальными и не расходуют бюджет чата. OpenRouter - отдельный сервис со своей
учётной записью, сетевым доступом и условиями использования. Tokenlogue не
аффилирован с OpenRouter. Подробнее о [хранении и сбросе](docs/user-guide.md#ru-data).

### Исходники и лицензии

Собственный код Tokenlogue доступен по [лицензии MIT](LICENSE).
[Обзор сторонних компонентов](THIRD_PARTY_NOTICES.md#lang-ru) описывает основные
зависимости и помогает найти уведомления о лицензиях внутри AppImage.

[Исходные материалы](docs/source-materials.md#lang-ru) включают исходники
приложения и отдельный комплект runtime. Руководство объясняет, какие
материалы доступны и чего пока не хватает для пересборки приложения без сети.

[English](#lang-en) | [Русский](#lang-ru)
