# Tokenlogue

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

<img src="docs/assets/tokenlogue-logo-transparent.png" alt="Tokenlogue logo on a transparent background" width="128">

Tokenlogue is a desktop application for chatting with AI models through
OpenRouter. It saves conversations and unsent drafts on your device and lets
you set token and spending limits for each chat. The published Linux preview has a Russian interface. Builds from the current
source also offer English.

### Download and launch

The current [published Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3)
is `0.1.0` from commit `2b1f7d3`. It provides the
[AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage)
and the [SHA256SUMS checksum file](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SHA256SUMS).
No GitHub sign-in is needed. Follow the [Linux guide](docs/linux-appimage.md#lang-en)
to download all six preview files, check SHA256SUMS and run the application.

| File | SHA-256 |
| --- | --- |
| `Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage` | `0852f9432cb089e31fef2722d84ce7124714588afb65d6f25cd64d0616a4779d` |

You need an x86-64-v2 compatible processor, system GTK3, graphics drivers
and a working Secret Service for storing the API key. You do not need to install Python, uv or Flutter SDK separately.

This preview is unsigned and does not update automatically.
Public release downloads do not include Windows, Android, DEB or RPM packages.

### How to use the published Linux preview

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

### Current source and new Android builds

Builds made from the current source offer `Русский / English` before sign-in.
After sign-in, use `Interface language` in `⋮`. Your choice is remembered.
Switching language keeps your typed PIN, draft and open dialog. Your messages
and chat titles stay in their original language.

The button at the top left hides or shows the chat list in a wide window
and opens it as a drawer in a narrow window. Hiding the wide panel gives
the conversation and editor more space. The wide-window choice is remembered
after locking, restarting or resizing the app.
See [language and chat panel controls](docs/user-guide.md#en-workspace).

After checking your OpenRouter key, choose a PIN. With English selected,
enter four digits from `0` to `9` in `PIN` and repeat them in `Repeat PIN`.
Leading zeros are allowed. `Suggest PIN` suggests a value that you can edit.
Save your chosen PIN and finish with `Save PIN`.
Changing or generating the PIN clears its repeat field. The eye button lets
you reveal the value. It is never copied to the clipboard automatically.

After signing in, open `⋮` and choose `Replace OpenRouter key` to change any
saved API key, including a valid one. You can cancel the confirmation and keep
using the current key. Replacement keeps your app PIN and conversations.

On Android, moving the app to the background locks access to chats. Returning
to the app requires your PIN. The selected chat, history and draft are kept.
An update preserves your existing PIN and does not require resetting access.
See [setup and locking in current builds](docs/user-guide.md#en-current).
These changes are not included in the published Linux preview `2b1f7d3`.

### Where your data is stored

The published Linux preview `2b1f7d3` stores history and drafts without
additional content encryption. Builds from the current source protect local
chat titles, messages and drafts with a separate encryption key kept in the
platform's secure storage. Dates, model information and budget metadata remain
readable. This protects conversation content in local files, not the entire
SQLite database or a compromised running device. Protect your operating-system
account and backups.

Before the first protected sign-in on Linux, close all older Tokenlogue copies
that use the same data folder. Current builds allow one process per data folder.
Do not run an older version alongside the conversion.

On Android 11 or later, use `Forgot PIN?` to start a new device security check, then choose
a new app PIN while keeping your conversations. Device PIN, pattern or password
can be used, with supported biometrics as an alternative. Linux has no device
recovery flow. Keep your existing app PIN. A new OpenRouter key cannot unlock
old protected conversations. Recovery also needs the original encryption key
to remain available. See [local protection and recovery](docs/user-guide.md#en-data).

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
application source, the published baseline from preview `986c6ad` and its
separate runtime bundle. Use that baseline together with
`Tokenlogue-2b1f7d3-source-supplement.tar.gz` for the current preview.
The [published source-material instructions](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SOURCE_MATERIALS.md#lang-en)
explain how to download, restore and select the collected files. Completeness
of the full source set and a full offline rebuild remain unverified.
The source review status remains `REVIEW_REQUIRED`.

<a name="lang-ru"></a>

## Русский

<img src="docs/assets/tokenlogue-logo-transparent.png" alt="Логотип Tokenlogue на прозрачном фоне" width="128">

Tokenlogue - настольное приложение для общения с моделями ИИ через OpenRouter.
Оно сохраняет переписку и неотправленные черновики на вашем устройстве
и позволяет задавать лимиты токенов и расходов для каждого чата.
Интерфейс опубликованной сборки для Linux на русском языке. В сборках
из текущих исходников также доступен английский.

### Скачивание и запуск

Текущая [опубликованная предварительная версия для Linux](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3)
имеет номер `0.1.0` и собрана из коммита `2b1f7d3`. Для неё доступны
[AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage)
и [файл контрольных сумм SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SHA256SUMS).
Вход в GitHub не нужен. Следуйте [руководству для Linux](docs/linux-appimage.md#lang-ru),
чтобы скачать все шесть файлов предварительной версии, проверить SHA256SUMS
и запустить приложение.

| Файл | SHA-256 |
| --- | --- |
| `Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage` | `0852f9432cb089e31fef2722d84ce7124714588afb65d6f25cd64d0616a4779d` |

Нужны процессор с поддержкой x86-64-v2, системная GTK3, видеодрайверы
и работающий Secret Service для хранения API-ключа. Отдельно устанавливать Python, uv или Flutter SDK не нужно.

У этой предварительной сборки нет цифровой подписи и автоматического обновления.
В опубликованных выпусках нет пакетов для Windows и Android, а также DEB и RPM.

### Как пользоваться опубликованной сборкой для Linux

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

### Текущие исходники и новые сборки Android

В сборках из текущих исходников до входа доступен переключатель
`Русский / English`. После входа откройте `Язык интерфейса` в `⋮`.
Выбор сохраняется. Смена языка не очищает введённый PIN и черновик
и не закрывает открытый диалог. Сообщения и названия чатов сохраняют свой язык.

Кнопка слева в шапке скрывает и показывает список чатов в широком окне
и открывает его как выдвижную панель в узком окне. При скрытой широкой панели
переписка и редактор занимают освободившееся место. Выбор для широкого окна
сохраняется после блокировки, перезапуска и изменения размеров приложения.
Подробнее в разделе [о языке и панели чатов](docs/user-guide.md#ru-workspace).

После проверки ключа OpenRouter можно выбрать собственный PIN. Введите четыре цифры от `0` до `9` в поле `PIN` и повторите
их в поле `Повторите PIN`. Начальные нули допустимы. Кнопка `Предложить PIN`
подставляет значение, которое можно изменить. Сохраните выбранный PIN
и завершите настройку кнопкой `Сохранить PIN`. Изменение или генерация PIN
очищает поле повторного ввода. Кнопка с глазом позволяет показать значение.
Автоматического копирования в буфер обмена нет.

После входа откройте `⋮` и выберите `Заменить ключ OpenRouter`, чтобы сменить
любой сохранённый API-ключ, в том числе действительный. Можно отменить
подтверждение и продолжить работу с текущим ключом. Замена сохраняет PIN
приложения и переписку.

В Android переход приложения в фон блокирует доступ к чатам. После возврата
нужно ввести PIN. Выбранный чат, история и черновик сохраняются. Обновление
сохраняет прежний PIN и не требует сброса доступа. Подробнее в разделе
[о настройке и блокировке текущих сборок](docs/user-guide.md#ru-current).
Эти изменения не входят в опубликованную сборку для Linux `2b1f7d3`.

### Где хранятся ваши данные

Опубликованная сборка для Linux `2b1f7d3` хранит историю и черновики без
дополнительного шифрования содержимого. Сборки из текущих исходников защищают
локальные названия чатов, сообщения и черновики отдельным ключом шифрования
в платформенном защищённом хранилище. Даты, сведения о моделях и бюджетах
остаются читаемыми. Защита относится к содержимому переписки в локальных
файлах, а не ко всей базе SQLite или скомпрометированному работающему
устройству. Защищайте свою учётную запись ОС и резервные копии.

Перед первым входом с защитой переписки в Linux закройте все прежние копии
Tokenlogue, использующие тот же каталог данных. Текущие сборки допускают один
процесс на каталог данных. Не запускайте прежнюю версию во время преобразования.

В Android 11 или новее нажмите `Забыли PIN?`, пройдите новую системную проверку защиты
устройства и выберите новый PIN приложения с сохранением переписки.
Можно использовать PIN, графический ключ или пароль устройства, а также
поддерживаемую биометрию. В Linux такого восстановления нет. Сохраните
прежний PIN приложения. Новый ключ OpenRouter не открывает старую защищённую
переписку. Для восстановления также нужен сохранившийся ключ шифрования.
Подробнее в разделе [о локальной защите и восстановлении](docs/user-guide.md#ru-data).

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
содержит ссылки на код приложения, опубликованный базовый комплект версии
`986c6ad` и его отдельный комплект runtime. Для текущей предварительной версии
используйте этот базовый комплект вместе с
`Tokenlogue-2b1f7d3-source-supplement.tar.gz`.
[Инструкция к опубликованным исходным материалам](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SOURCE_MATERIALS.md#lang-ru)
объясняет, как скачать, восстановить и выбрать собранные файлы. Полнота всего
исходного набора и полная пересборка без сети остаются непроверенными.
Статус проверки исходных материалов остаётся `REVIEW_REQUIRED`.
