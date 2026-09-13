# Tokenlogue

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

<img src="docs/assets/tokenlogue-icon-512.png" alt="Tokenlogue application icon" width="128">

Tokenlogue is a desktop application for chatting with AI models through
OpenRouter. It saves conversations and unsent drafts on your device and lets
you set token and spending limits for each chat. The application interface
is currently in Russian.

### Download and launch

The [Linux guide](docs/linux-appimage.md#lang-en) explains how to download
`Tokenlogue-0.1.0-1472c00-x86_64.AppImage`, check its SHA-256 and run it.
You need an x86-64-v2 compatible processor, system GTK3, graphics drivers
and a working Secret Service for storing the API key. You do not need to install Python, uv or Flutter SDK separately.

This unsigned preview is distributed through GitHub Actions with limited
retention. It does not update automatically. Ready-to-use Windows, Android, DEB
and RPM packages are not available.

### How to use Tokenlogue

1. Enter your OpenRouter API key. After the key is checked, save the generated
   four-digit PIN. You will use it to unlock the application on later launches.
2. Create a chat with `+`. Choose a free or paid mode and a model, then set
   the chat's token limit. For a paid chat, also set a spending limit.
3. Type a message and send it. Tokenlogue asks for confirmation before each
   paid request and before increasing a chat's spending limit.

Conversation history and a separate draft for each chat are saved
automatically. You can switch chats or restart the application and continue
where you left off.

Open `⋮` at the far right of the header to view the key status, chat mode,
model, token usage and spending. The same menu lets you change limits,
rename a chat or delete it. The `+` and lock buttons remain beside the menu.
In a narrow window, the button at the top left opens the chat list.

The [user guide](docs/user-guide.md#lang-en) covers setup, keyboard controls,
drafts, budget reservations and what to do if a request's result is unknown.

### Where your data is stored

History and drafts are stored in a local SQLite database without additional
content encryption. The PIN controls access through the application interface
and is not stored as plain text. The API key is kept separately in the
platform's SecureStorage. Protect your operating-system account and backups.

When you send a message, its text and conversation context go to OpenRouter
and the selected model provider. Unsent drafts stay on your device and do not
consume tokens or money. You need an OpenRouter account and an internet
connection to use the service. OpenRouter has its own usage and data terms.
Tokenlogue is an independent application and is not affiliated with OpenRouter.
See [data storage and reset](docs/user-guide.md#en-data) for details.

### Source code and licenses

Tokenlogue's own code is available under the [MIT License](LICENSE).
The [third-party software overview](THIRD_PARTY_NOTICES.md#lang-en) lists the
main dependencies and explains where to find their licenses in the AppImage.

The [source materials guide](docs/source-materials.md#lang-en) links to the
application source and a separate runtime bundle. It also explains which
materials are still missing for rebuilding the full application offline.

<a name="lang-ru"></a>

## Русский

<img src="docs/assets/tokenlogue-icon-512.png" alt="Значок приложения Tokenlogue" width="128">

Tokenlogue - настольное приложение для общения с моделями ИИ через OpenRouter.
Оно сохраняет переписку и неотправленные черновики на вашем устройстве
и позволяет задавать лимиты токенов и расходов для каждого чата.
Интерфейс приложения сейчас на русском языке.

### Скачивание и запуск

В [руководстве для Linux](docs/linux-appimage.md#lang-ru) описано, как скачать
`Tokenlogue-0.1.0-1472c00-x86_64.AppImage`, проверить его SHA-256 и запустить.
Нужны процессор с поддержкой x86-64-v2, системная GTK3, видеодрайверы
и работающий Secret Service для хранения API-ключа. Отдельно устанавливать Python, uv или Flutter SDK не нужно.

Эта неподписанная предварительная сборка распространяется через GitHub Actions
с ограниченным сроком хранения. Автоматического обновления нет. Готовых пакетов
для Windows и Android, а также пакетов DEB и RPM пока нет.

### Как пользоваться Tokenlogue

1. Введите API-ключ OpenRouter. После проверки ключа сохраните созданный
   четырёхзначный PIN. Он понадобится для входа при следующих запусках.
2. Создайте чат кнопкой `+`. Выберите бесплатный или платный режим и модель,
   затем задайте лимит токенов. Для платного чата также укажите лимит расходов.
3. Напишите и отправьте сообщение. Перед каждым платным запросом
   и увеличением денежного лимита чата приложение запросит подтверждение.

История переписки и отдельный черновик каждого чата сохраняются автоматически.
Можно переключиться в другой чат или перезапустить приложение, а затем
продолжить с того же места.

Откройте `⋮` в правом краю шапки, чтобы посмотреть состояние ключа, режим чата,
выбранную модель, расход токенов и денег. В этом же меню можно изменить лимиты,
переименовать или удалить чат. Кнопки `+` и блокировки находятся рядом с меню.
В узком окне кнопка слева вверху открывает список чатов.

[Руководство пользователя](docs/user-guide.md#lang-ru) объясняет настройку,
управление с клавиатуры, сохранение черновиков, резервирование бюджета
и действия при неизвестном результате запроса.

### Где хранятся ваши данные

История и черновики находятся в локальной базе SQLite без дополнительного
шифрования содержимого. PIN ограничивает доступ через интерфейс приложения
и не хранится открытым текстом. API-ключ сохраняется отдельно
в платформенном хранилище SecureStorage. Защищайте свою учётную запись ОС
и резервные копии.

При отправке сообщения его текст и контекст переписки передаются в OpenRouter
и выбранному поставщику модели. Неотправленные черновики остаются на устройстве
и не расходуют токены или деньги. Для работы сервиса нужны учётная запись
OpenRouter и подключение к интернету. У OpenRouter действуют собственные
условия использования и обработки данных. Tokenlogue разрабатывается независимо
от OpenRouter. Подробнее в разделе
[о хранении данных и сбросе доступа](docs/user-guide.md#ru-data).

### Исходный код и лицензии

Собственный код Tokenlogue доступен по [лицензии MIT](LICENSE).
[Обзор сторонних компонентов](THIRD_PARTY_NOTICES.md#lang-ru) перечисляет
основные зависимости и объясняет, где найти их лицензии внутри AppImage.

[Руководство по исходным материалам](docs/source-materials.md#lang-ru)
содержит ссылки на код приложения и отдельный комплект runtime. В нём также
описано, каких материалов пока не хватает для пересборки всего приложения
без подключения к сети.
