<p align="center">
  <img src="docs/assets/tokenlogue-logo-transparent.png" alt="Tokenlogue" width="104">
</p>

# Tokenlogue

[English](#english) · [Русский](#russian)

[Home / Главная](https://github.com/Umichata/tokenlogue/tree/main) · [Android](https://github.com/Umichata/tokenlogue/tree/android) · [**Linux**](https://github.com/Umichata/tokenlogue/tree/linux)

<a id="english"></a>
<a id="lang-en"></a>

## English

Chat with OpenRouter models from your Linux desktop. Tokenlogue provides a compact conversation workspace with saved drafts, model selection and a live cost estimate.

[Install](#en-install) · [First chat](#en-chat) · [Protection](docs/security.md#english)

<a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/screenshots/linux-chat.png" alt="Linux chat with local demonstration messages" width="760"></a>

Linux chat with local demonstration messages.

<a id="en-install"></a>
### Download and launch

The package is an **unsigned x86_64 AppImage**. You need an x86-64-v2 CPU, compatible desktop libraries and graphics drivers. Ubuntu 22.04 is the system-library baseline. Normal startup uses FUSE, with an extract-and-run option when FUSE is unavailable.

For this preview, choose `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` and `RELEASE_SHA256SUMS` from [Releases](https://github.com/Umichata/tokenlogue/releases). If this preview is not listed, its downloads are not public yet. The [earlier published Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) remains a historical package with its own release notes. The screenshot above shows the current interface.

Check only the selected AppImage against its entry in `RELEASE_SHA256SUMS` as explained in the Linux guide below, make it executable and run it as a normal user. For updates, close earlier copies before starting the replacement file. No separate Python, Flutter or Java installation or source archives are needed.

[Linux requirements, checksum and launch instructions](docs/linux-appimage.md#english)

<a id="en-chat"></a>
### Start a conversation

Add your OpenRouter key, let the application check it and set a PIN. Create a chat and choose a model. Drafts stay with each chat. Rename and delete controls are available beneath the conversation title.

The local estimate is approximate. A per-chat budget, an OpenRouter key limit and the account balance are different values. Disabling paid-request confirmation applies from the first request in that chat, while limits remain active.

[Chat and cost guide](docs/user-guide.md#english)

### Protect the local profile

A working Secret Service in your desktop session stores protected key material. Save the portable recovery code when offered and keep it separate from your computer. PIN and local field encryption do not encrypt the entire device. Without the required keys or recovery material, the application cannot promise to restore encrypted conversations.

[Protection and recovery](docs/security.md#english) · [Sources](docs/source-materials.md#english) · [AppImage licenses](packaging/linux/appimage/notices.md#english) · [MIT license](LICENSE)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Общайтесь с моделями OpenRouter на компьютере Linux. Tokenlogue предоставляет компактное пространство для переписки с черновиками, выбором модели и оценкой затрат во время набора.

[Установка](#ru-install) · [Первый чат](#ru-chat) · [Защита](docs/security.md#russian)

<a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/screenshots/linux-chat.png" alt="Чат Linux с локальными демонстрационными сообщениями" width="760"></a>

Чат Linux с локальными демонстрационными сообщениями.

<a id="ru-install"></a>
### Загрузка и запуск

Пакет поставляется как **неподписанная AppImage x86_64**. Нужны процессор x86-64-v2, совместимые библиотеки рабочего стола и видеодрайверы. Базовая версия системных библиотек соответствует Ubuntu 22.04. Обычный запуск использует FUSE, при его отсутствии можно запустить с распаковкой.

Для этой предварительной версии выберите `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` и `RELEASE_SHA256SUMS` на странице [Releases](https://github.com/Umichata/tokenlogue/releases). Если этой версии нет в списке, её загрузки ещё не опубликованы. [Прежний опубликованный Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) остаётся историческим пакетом с собственными примечаниями к выпуску. На снимке выше показан текущий интерфейс.

Проверьте только выбранную AppImage по её записи в `RELEASE_SHA256SUMS`, как описано в руководстве Linux ниже. Разрешите выполнение и запустите её от обычного пользователя. При обновлении закройте прежние копии перед открытием нового файла. Отдельная установка Python, Flutter или Java и архивы исходников не нужны.

[Требования Linux, проверка суммы и запуск](docs/linux-appimage.md#russian)

<a id="ru-chat"></a>
### Начало переписки

Добавьте свой ключ OpenRouter, дождитесь его проверки приложением и задайте PIN. Создайте чат и выберите модель. Черновики сохраняются для каждого чата. Действия переименования и удаления расположены под названием разговора.

Локальная оценка приблизительна. Бюджет чата, лимит ключа OpenRouter и баланс аккаунта — разные величины. Отключение подтверждения платного запроса действует с первого запроса выбранного чата, а лимиты продолжают работать.

[Руководство по чату и затратам](docs/user-guide.md#russian)

### Защита локального профиля

Работающий Secret Service в сеансе рабочего стола хранит защищённые материалы ключей. Сохраните переносимый резервный код, когда приложение предложит его, и храните отдельно от компьютера. PIN и шифрование отдельных полей не шифруют всё устройство. Без необходимых ключей или материалов восстановления нельзя обещать восстановление зашифрованной переписки.

[Защита и восстановление](docs/security.md#russian) · [Исходники](docs/source-materials.md#russian) · [Лицензии AppImage](packaging/linux/appimage/notices.md#russian) · [Лицензия MIT](LICENSE)
