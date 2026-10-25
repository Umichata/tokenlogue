# Tokenlogue - User guide / Руководство пользователя

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This guide describes the current [published `0.1.0` preview `2b1f7d3`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3).
The [current-source section](#en-current) describes newer setup, Android
locking, chat panel controls and language selection. Those changes are not
part of the published Linux preview. The published preview has a Russian
interface, so its instructions use Russian control labels. Current builds
also offer English. The current-build instructions below use English labels
when English is selected.
For installation of the published preview, use the
[Linux AppImage guide](linux-appimage.md#lang-en).

[Key and PIN in the Linux preview](#en-access) | [Current builds](#en-current) |
[Panel and language](#en-workspace) |
[Chats and menu](#en-chats) |
[Messages and drafts](#en-drafts) | [Limits](#en-limits) | [Data](#en-data)

<a name="en-access"></a>

### First launch and signing in to the published Linux preview

On first launch, enter your API key in `OpenRouter API-ключ` and choose
`Проверить ключ` (check key). Obtain a key through your OpenRouter account.
Checking it requires access to OpenRouter. A network error does not by itself
mean that the key is invalid.

After successful validation, Tokenlogue generates a four-digit PIN and shows
it once. Save all four digits, including any leading zero, then choose
`Я сохранил PIN` (I saved the PIN). The key is stored only after this
confirmation. At later launches, enter the PIN and choose `Войти` (sign in).
Five incorrect attempts cause a 30-second lockout.

Use the lock button in the header to return to the PIN screen. If you forget
the PIN or need to reset access, use `Сбросить ключ` (reset key) on that screen
and confirm. This removes the saved API key, PIN verification data and lockout
state. Existing chats and drafts remain. The next setup requires the key again
and generates a new PIN. This local reset does not revoke the key at OpenRouter.

After unlocking, check the key status through `⋮`. The panel shows whether the key is valid
and its remaining spending limit, if available. Depending on the key status, it offers
`Повторить проверку ключа` (check again) or `Заменить ключ` (replace key).
Opening the menu alone does not recheck the key or send a model request.
The key's spending limit is separate from the local limit of each chat.

<a name="en-current"></a>

### Choosing a PIN and locking in current builds

This section applies to builds made from the current source, including new
Android builds. The published Linux preview `2b1f7d3` keeps the setup described
[above](#en-access).

After your OpenRouter key has been checked, the `Choose a PIN` screen opens with an empty `PIN` field. Choose exactly four digits from `0`
to `9`. Leading zeros are allowed. Repeat the value in `Repeat PIN`. Spaces, other characters and digits from other writing systems
are not accepted.

You can choose `Suggest PIN` to fill the first field with a
random value. You can edit that value before saving. Any change to the first
field or a new suggestion clears the repeat field, even if the suggested
number happens to be the same. `Save PIN` is available only
when both fields contain the same valid PIN and no operation is in progress.
A suggestion alone does not complete setup.

Both fields hide their contents. Use the eye button to reveal the PIN when
you need to check or save it somewhere safe. Tokenlogue does not copy it to
the clipboard automatically. The checked key and PIN verification data are
saved when you confirm setup. If you leave an unfinished Android setup in
the background, enter the key again when you return and choose a PIN again.

On Android, moving Tokenlogue to the background locks access to chats and
closes open dialogs. Returning to the app or unlocking Android does not
unlock Tokenlogue. Enter your PIN to continue with the selected chat,
history and draft. Opening the keyboard or briefly losing focus alone does
not lock the app. The header lock button remains available on every platform.

Updating an existing installation keeps its PIN, including a PIN generated
by an older version. You do not need to reset access to use the update.
Five incorrect sign-in attempts still cause a 30-second lockout.

To replace any saved OpenRouter API key, first sign in with your current app
PIN. Open `⋮` and choose `Replace OpenRouter key`. This action is available for
valid, invalid, restricted and unknown key status, with or without a selected
chat. It stays visible while a key check or send operation is running and
becomes available when that operation finishes or is cancelled.

You can cancel the confirmation and continue with your current key and draft.
If you confirm, enter another API key and check it. The saved key stays in
place until the new key passes validation and is saved. If checking or saving
fails, you can try again. Your app PIN, encryption key, conversations, drafts
and budgets stay the same. There is no new PIN setup. `Refresh key status`
remains a separate action and keeps the menu open. Replacing an API key does
not recover a forgotten PIN or revoke the previous key at OpenRouter.

On Android 11 or later, `Forgot PIN?` starts a separate system check of the device PIN,
pattern or password. Supported biometrics may be offered as an alternative.
A fingerprint is not required. The device needs to have a supported screen
lock configured. Merely unlocking the screen does not complete this new check.
After successful verification, choose a new four-digit app PIN, repeat it
and select `Save new PIN`. `Suggest PIN` remains available. The workspace
stays closed until the new PIN is saved. Cancelling before that confirmation
keeps the previous PIN and conversations. If the system check fails or is
cancelled, sign in with your previous PIN or start a new check.

Device recovery is unavailable on Android 7–10 and on Linux. Normal app PIN
sign-in remains available. Keep your app PIN somewhere safe.
Entering a valid OpenRouter key and choosing another PIN cannot open an
existing protected conversation database. Recovery on Android also depends
on the original protected encryption key still being available.

In current builds, `Rename` and `Delete chat`
appear directly below the selected chat's title, even when the menu is closed.
A name you save here stays unchanged after later messages and restarts.
Renaming preserves the conversation and draft. Deletion asks for confirmation
and removes only that chat's local history and draft. Key status, model
information and limits remain in `⋮`.

<a name="en-workspace"></a>

### Language and chat panel in current builds

Choose `Русский / English` before signing in. The selector is also available
while choosing a PIN or when storage is unavailable. After signing in, open
`⋮` and change `Interface language`. Russian is used until you choose English.
Your choice is remembered after restarting, locking and updating the app or
replacing the OpenRouter key.

The new language applies immediately to the current screen and open dialogs.
Your typed PIN, chat title, limit values and draft remain in place. Switching
language does not repeat a key check or send a message. Messages, model
responses and your chat titles are not translated. The built-in label for
a new unnamed chat follows the interface language. Existing titles stay as
saved when their origin is uncertain. A title taken from your first message
also stays in its original language.

The button at the top left is always available. In a wide window it hides
or shows the chat list. With the list hidden, the conversation and editor
use the freed space. The app remembers the wide-window choice when you
switch chats, refresh key status, lock, sign in again or restart.

In a narrow window the same button opens a drawer. Select a chat, press
Escape or Back, or tap outside the drawer to close it. Switching language
keeps an explicitly opened drawer open. A narrow window does not change
your saved wide-window choice. That choice returns when the window becomes
wide again. The selected chat, reading position, draft and pending request
are preserved when you toggle the panel or language.

`Rename` and `Delete chat` remain below the selected title. The `+` and lock
buttons stay at the right, with `⋮` at the far right. If the menu contains
more information than fits on screen, scroll inside it.

<a name="en-chats"></a>

### Creating and managing chats

Choose `+` with the tooltip `Новый чат` (new chat). Select free or paid mode,
find a model by name or ID in `Поиск модели`, then configure the chat limits.
Paid mode includes a warning about possible charges.

Free mode offers automatic model selection through `openrouter/free` and
models whose applicable prices are all zero. Tokenlogue checks the prices
reported by OpenRouter, rather than relying on the model name or `:free` suffix.
Free requests are still subject to the service's availability and request limits.
Paid mode also requires a valid key and available model information.
OpenRouter checks your account balance when processing a paid request.

Each chat keeps its selected mode and model. To use another mode or model,
create another chat. The menu shows the model selected for the chat.
If you choose automatic model selection, this is the router's name.
OpenRouter then chooses the model that processes each request.

In a wide window, use the chat list on the left. In a narrow window, the
left header button `Открыть список чатов` opens that list. Select a chat to
restore its conversation and draft. A long chat title is shortened visually
in the header and remains available through its tooltip.

The `⋮` button, labelled `Параметры чата` (chat settings), is on the right
after the new-chat and lock buttons. Its scrollable panel opens over the
conversation. Activate the focused button with Enter or Space. Close the panel
with Escape, its close button or a click outside it.

| Menu area | What it contains |
| --- | --- |
| `Ключ OpenRouter` | Key status, known key limit and the actions available for that state. |
| `Чат` | Free or paid mode, model name and ID, and token prices for paid chats. |
| `Токены и бюджет` | Used, reserved and remaining tokens, response maximum, and costs for paid chats. |
| `Настроить лимиты` or `Изменить лимиты` | Configure or change the active chat's limits. |
| `Переименовать` | Change the active chat's title. |
| `Удалить чат` | Delete the active chat after confirmation. |

Opening or closing the menu does not send the draft or erase it. The editor
stays at the bottom. Renaming preserves the conversation and draft.
Deleting a chat removes its local history and draft. Cancel the confirmation
to keep it. Renaming, deletion and limit changes are disabled while sending.

<a name="en-drafts"></a>

### Sending messages and saving drafts

Type in `Сообщение` (message). Press Enter to send or use `Отправить` (send).
Shift+Enter inserts a new line. Empty or whitespace-only messages cannot be sent.
While a response is pending, the editor displays its waiting state.
In current builds, longer drafts scroll vertically inside the editor on narrow screens.

Each chat automatically saves its own draft locally. Switching chats,
resizing the window, renaming a chat and restarting restore the saved text,
including text in any language, spaces and line breaks. Drafts are separate from message
history. They are not sent as context and do not use tokens or money.

After Tokenlogue adds your message to the conversation and starts sending it,
the submitted draft is cleared. The reply may arrive later. If you begin a new
draft, completion of the previous request will not erase it. A failed check
before sending or a cancelled paid request leaves the original draft in place.

Sending transmits the message and conversation context to OpenRouter.
Long histories therefore affect both the input size and the budget needed for
the next request. View the response or request status in the conversation.

<a name="en-limits"></a>

### How token and spending limits work

Configure limits before the first send. Tokenlogue distinguishes these settings:

| Setting | Meaning |
| --- | --- |
| `Общий лимит токенов чата` | Total input and output token budget for the chat's requests. |
| `Максимум токенов одного ответа` | Maximum output tokens requested for the next response. |
| `Денежный лимит чата, USD` | Local spending cap for a paid chat. |

The total budget also accounts for conversation context sent again with later
messages. The response maximum sets an upper limit. The actual response can be shorter. Before sending, Tokenlogue reserves tokens and, for paid chats,
money. It can refuse a request when the available budget cannot cover that reserve.

Open `⋮` to see how much of the budget has been used, reserved or remains
available. Reserved amounts are set aside for requests that are still pending
or have an unknown result. They cannot be used for a new request until
released. An unknown cost is not treated as zero. A reservation is a local
budget limit, not a charge to your OpenRouter account. Check that account
for the service's actual billing records.

Each paid request has a confirmation showing its model and estimated reserve.
If prices change, another confirmation is required. Increasing a chat's
monetary cap also requires confirmation. Cancel the dialog to leave the request unsent or keep the previous limit.

#### If a request's result is unknown

If a connection fails after a request may have reached OpenRouter, Tokenlogue
keeps a protective reserve. The conversation shows that the result is unknown.
The service may still have processed and billed the request.

Check the request and usage in your OpenRouter account before sending again.
After checking the request, you can choose `Освободить резерв` (release reserve)
and confirm if you want to make that budget available again. It releases the local reservation. It does not
cancel a remote request or refund a charge. Retrying can create another charge.

<a name="en-data"></a>

### Data storage and access

In the published Linux preview `2b1f7d3`, chats, messages, drafts, budget state
and PIN verification data are stored in the local application database without
additional content encryption. The PIN is not stored as plain text, but it only restricts access
through Tokenlogue's interface. Someone with access to your OS account or
database files may be able to read the history and drafts.

The API key and registration identifier are stored separately in platform
SecureStorage. On Linux this requires a working Secret Service.
Resetting the key preserves chats and drafts, while deleting a chat removes
that chat's local content. Neither action deletes records held by OpenRouter
or a model provider. Replacing the AppImage file does not remove application data.


#### Local content protection in current builds

Current builds encrypt saved chat titles, user and model messages, and drafts.
The encryption key is randomly generated and kept separately in platform secure
storage. It is not derived from your four-digit app PIN or OpenRouter key.
Your PIN controls access to that key through Tokenlogue. On Linux, a working
Secret Service is required. If secure storage or the encryption key is
unavailable, the app keeps conversations closed rather than saving their
contents without protection.

On the first successful sign-in after updating older local data, Tokenlogue
protects the existing content before opening the chat workspace. History,
drafts and their revisions, chat IDs, model choices and financial accounting
are preserved. If the conversion cannot finish, the app reports an error and
keeps the data. Do not delete the database or reset device security to dismiss
that error.

If a temporary secure storage error interrupts the initial setup of protection,
try signing in again with your existing app PIN after storage becomes available.
Tokenlogue can finish a confirmed incomplete setup while keeping your data.
This does not recreate a lost key for conversations that are already encrypted.

On Linux, close all older Tokenlogue copies that use this data folder before
the first protected sign-in. Keep them closed during conversion and while using
the updated app. Current builds allow one process per data folder and ask a
second process to close the other copy. Older versions do not follow that rule.

This is encryption of selected content fields. Structural information remains
readable, including dates, model IDs, chat modes, token counts, budgets and
accounting status. It is not encryption of the whole SQLite database and is
not end-to-end encryption with OpenRouter. Sending still transmits the required
message content and context to OpenRouter and the chosen model provider.

Locking clears the visible workspace and blocks new access. A request already
sent may still finish and save its response and accounting in protected form.
This does not guarantee instant erasure of every plaintext or key copy from
a running process. It does not protect an already compromised operating system.

Protection applies to the app's current accessible files after conversion.
Older external copies and previously written flash or SSD blocks may retain
older content. Android application backup remains disabled. Copying the database
to another device does not transfer its protected key. Uninstalling the app,
resetting its data, losing secure storage or invalidating Android Keystore can
make protected history unrecoverable. Changes to device security can affect
key availability on some devices. A new app PIN or API key cannot recreate a
lost encryption key.

Tokenlogue is a client of the separate OpenRouter service and is not affiliated
with it. Review the service's and model provider's data terms before sending
private content.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Руководство описывает текущую [опубликованную предварительную сборку `0.1.0` версии `2b1f7d3`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3).
[Раздел о текущих исходниках](#ru-current) описывает новую настройку PIN
и блокировку Android в сборках из текущих исходников. Эти изменения не входят
в опубликованную сборку для Linux. Интерфейс на русском языке. Ниже используются
названия элементов, которые видны в приложении. Установка опубликованной
сборки описана в [руководстве по AppImage для Linux](linux-appimage.md#lang-ru).

[Ключ и PIN в сборке Linux](#ru-access) | [Текущие сборки](#ru-current) |
[Панель и язык](#ru-workspace) |
[Чаты и меню](#ru-chats) |
[Сообщения и черновики](#ru-drafts) | [Лимиты](#ru-limits) | [Данные](#ru-data)

<a name="ru-access"></a>

### Первый запуск и вход в опубликованную сборку для Linux

При первом запуске введите свой ключ в поле `OpenRouter API-ключ` и нажмите
`Проверить ключ`. Получить ключ можно в своей учётной записи OpenRouter.
Для проверки нужен доступ к OpenRouter. Сетевая ошибка сама по себе не
означает, что ключ недействителен.

После успешной проверки Tokenlogue создаёт четырёхзначный PIN и показывает
его один раз. Сохраните все четыре цифры, включая начальный ноль, если он есть,
затем нажмите `Я сохранил PIN`. Ключ записывается в хранилище только после
этого подтверждения. При следующих запусках введите PIN и нажмите `Войти`.
После пяти неверных попыток вход блокируется на 30 секунд.

Кнопка блокировки в шапке возвращает на экран PIN. Если PIN забыт или нужно
сбросить доступ, нажмите на этом экране `Сбросить ключ` и подтвердите действие.
Сохранённый API-ключ, проверочные данные PIN и состояние блокировки будут
удалены. Существующие чаты и черновики останутся. При повторной настройке
нужно снова ввести ключ и сохранить новый PIN. Локальный сброс не отзывает
ключ в OpenRouter.

После входа откройте `⋮`, чтобы проверить состояние ключа. В меню видно, действителен ли ключ
и сколько средств осталось в его расходном лимите, если эти данные доступны.
В зависимости от состояния ключа можно выбрать `Повторить проверку ключа` или `Заменить ключ`.
Само открытие меню не проверяет ключ заново и не отправляет запрос модели.
Расходный лимит ключа отделён от локального лимита каждого чата.

<a name="ru-current"></a>

### Выбор PIN и блокировка в текущих сборках

Этот раздел относится к сборкам из текущих исходников, включая новые сборки
Android. В опубликованной версии для Linux `2b1f7d3` остаётся настройка,
описанная [выше](#ru-access).

После проверки ключа OpenRouter открывается экран `Выберите PIN` с пустым
полем `PIN`. Выберите ровно четыре цифры от `0` до `9`. Начальные нули
допустимы. Повторите значение в поле `Повторите PIN`. Пробелы, другие символы
и цифры из других систем письма не принимаются.

Кнопка `Предложить PIN` заполняет первое поле случайным значением. Его можно
изменить до сохранения. Любая правка первого поля или новое предложение
очищают поле повторного ввода, даже если предложенное число совпало
с предыдущим. Кнопка `Сохранить PIN` доступна только при совпадении двух
корректных значений и отсутствии текущей операции. Одно предложение PIN
не завершает настройку.

Оба поля скрывают содержимое. Кнопка с глазом позволяет показать PIN,
чтобы проверить его или сохранить в безопасном месте. Tokenlogue не копирует
его в буфер обмена автоматически. Проверенный ключ и проверочные данные PIN
сохраняются после подтверждения настройки. Если незавершённая настройка
в Android прервана переходом в фон, после возврата нужно снова ввести ключ
и выбрать PIN.

В Android переход Tokenlogue в фон блокирует доступ к чатам и закрывает
открытые диалоги. Возврат в приложение или разблокировка Android не открывают
Tokenlogue. Введите PIN, чтобы продолжить работу с выбранным чатом,
историей и черновиком. Открытие клавиатуры или краткая потеря фокуса сами
по себе не блокируют приложение. Кнопка блокировки в шапке остаётся доступной
на всех платформах.

Обновление установленного приложения сохраняет прежний PIN, в том числе
созданный старой версией. Для использования обновления не нужен сброс доступа.
После пяти неверных попыток вход по-прежнему блокируется на 30 секунд.

Чтобы заменить любой сохранённый API-ключ OpenRouter, сначала войдите
с действующим PIN приложения. Откройте `⋮` и выберите `Заменить ключ OpenRouter`.
Действие доступно при действительном, недействительном, ограниченном
и неизвестном статусе ключа, в том числе без выбранного чата. Во время проверки
ключа или отправки оно остаётся видимым и становится доступным после
завершения или отмены операции.

Можно отменить подтверждение и продолжить работу с текущим ключом и черновиком.
Если подтвердите замену, введите другой API-ключ и проверьте его. Сохранённый
ключ останется на месте до успешной проверки и сохранения нового. Если
проверка или сохранение не удались, можно повторить попытку. PIN приложения,
ключ шифрования, переписка, черновики и бюджеты сохранятся. Заново выбирать
PIN не нужно. `Обновить статус ключа` остаётся отдельным действием и оставляет
меню открытым. Замена API-ключа не восстанавливает забытый PIN и не отзывает
прежний ключ в OpenRouter.

В Android 11 или новее кнопка `Забыли PIN?` запускает отдельную системную проверку PIN,
графического ключа или пароля устройства. Поддерживаемая биометрия может
предлагаться как другой способ. Отпечаток пальца не обязателен. На устройстве
должна быть настроена поддерживаемая блокировка экрана. Обычная разблокировка
экрана не завершает эту новую проверку. После успешного подтверждения выберите
новый четырёхзначный PIN приложения, повторите его и нажмите
`Сохранить новый PIN`. Кнопка `Предложить PIN` остаётся доступной.
Переписка закрыта до сохранения нового PIN. Отмена до этого подтверждения
сохраняет прежний PIN и переписку. Если системная проверка не прошла или
отменена, войдите с прежним PIN либо начните новую проверку.

В Android 7–10 и Linux системное восстановление недоступно. Обычный вход
по PIN приложения продолжает работать. Сохраните PIN приложения
в надёжном месте. Ввод действительного ключа OpenRouter и выбор другого PIN
не открывают существующую защищённую базу переписки. Для восстановления
в Android также нужен сохранившийся защищённый ключ шифрования.

В текущих сборках кнопки `Переименовать` и `Удалить чат` находятся прямо
под названием выбранного чата и видны при закрытом меню. Сохранённое здесь
название не меняется после новых сообщений и перезапуска. Переименование
сохраняет переписку и черновик. Удаление требует подтверждения и убирает
только локальную историю и черновик этого чата. Состояние ключа, сведения
о модели и лимиты остаются в `⋮`.

<a name="ru-workspace"></a>

### Язык и панель чатов в текущих сборках

Выберите `Русский / English` до входа. Переключатель также доступен при выборе
PIN и на экране недоступного хранилища. После входа откройте `⋮` и измените
`Язык интерфейса`. Пока вы не выбрали английский, используется русский.
Выбор сохраняется после перезапуска, блокировки, обновления приложения
и замены ключа OpenRouter.

Новый язык сразу применяется к текущему экрану и открытым диалогам.
Введённый PIN, название чата, значения лимитов и черновик остаются на месте.
Смена языка не повторяет проверку ключа и не отправляет сообщение.
Сообщения, ответы модели и ваши названия чатов не переводятся. Служебная
подпись нового чата без названия следует языку интерфейса. Старые названия
сохраняются как записаны, если их происхождение неизвестно. Название,
полученное из первого сообщения, также остаётся на исходном языке.

Кнопка слева в шапке доступна постоянно. В широком окне она скрывает
и показывает список чатов. Когда список скрыт, переписка и редактор
занимают освободившееся место. Приложение запоминает выбор для широкого
окна при смене чата, обновлении состояния ключа, блокировке, повторном
входе и перезапуске.

В узком окне та же кнопка открывает выдвижную панель. Выберите чат,
нажмите Escape или Back либо коснитесь области за панелью, чтобы закрыть её.
Смена языка сохраняет явно открытую панель. Узкое окно не меняет
сохранённый выбор для широкого режима. Этот выбор возвращается,
когда окно снова становится широким. Выбранный чат, позиция чтения,
черновик и текущая отправка сохраняются при переключении панели и языка.

`Переименовать` и `Удалить чат` остаются под выбранным названием.
Кнопки `+` и блокировки находятся справа, а `⋮` занимает крайнее правое
место. Если сведения меню не помещаются на экран, прокрутите его.

<a name="ru-chats"></a>

### Создание чатов и управление ими

Нажмите `+` с подсказкой `Новый чат`. Выберите бесплатный или платный режим,
найдите модель по названию или ID в поле `Поиск модели`, затем настройте
лимиты чата. При выборе платного режима показывается предупреждение о расходах.

В бесплатном режиме доступны автоматический выбор модели через
`openrouter/free` и модели с нулевой стоимостью всех применимых услуг.
Tokenlogue проверяет цены, полученные от OpenRouter. Одного названия модели
или суффикса `:free` для этого недостаточно. Бесплатные запросы также зависят
от доступности сервиса и ограничений на число запросов. Для платного режима
нужны действующий ключ и сведения о моделях. OpenRouter проверяет баланс
вашей учётной записи при обработке платного запроса.

Чат сохраняет выбранные режим и модель. Для другого режима или модели
создайте новый чат. В меню указана выбранная для чата модель.
При автоматическом выборе здесь отображается название маршрутизатора.
Модель для обработки каждого запроса в этом случае выбирает OpenRouter.

В широком окне список чатов находится слева. В узком окне он открывается
левой кнопкой шапки с подсказкой `Открыть список чатов`. Выберите чат, чтобы
восстановить его переписку и черновик. Длинное название сокращается в шапке
только визуально и остаётся доступным во всплывающей подсказке.

Кнопка `⋮` с подсказкой `Параметры чата` находится справа после кнопок
нового чата и блокировки. Прокручиваемая панель открывается поверх переписки.
Кнопку в фокусе можно активировать клавишей Enter или Space. Закрыть панель
можно по Escape, кнопкой закрытия или нажатием вне панели.

| Область меню | Содержимое |
| --- | --- |
| `Ключ OpenRouter` | Состояние ключа, известный лимит ключа и доступные при этом состоянии действия. |
| `Чат` | Бесплатный или платный режим, название и ID модели, цены токенов для платного чата. |
| `Токены и бюджет` | Использованные, зарезервированные и оставшиеся токены, максимум ответа, расходы платного чата. |
| `Настроить лимиты` или `Изменить лимиты` | Настройка или изменение лимитов активного чата. |
| `Переименовать` | Изменение названия активного чата. |
| `Удалить чат` | Удаление активного чата после подтверждения. |

Открытие и закрытие меню не отправляют и не стирают черновик. Редактор остаётся
внизу. Переименование сохраняет переписку и черновик. При удалении чата
удаляются его локальная история и черновик. Отмените подтверждение, чтобы
сохранить чат. Во время отправки переименование, удаление и изменение лимитов
недоступны.

<a name="ru-drafts"></a>

### Отправка сообщений и сохранение черновиков

Введите текст в поле `Сообщение`. Для отправки нажмите Enter или кнопку
`Отправить`. Shift+Enter добавляет перенос строки. Пустое сообщение или
сообщение только из пробелов отправить нельзя. Пока ответ не получен,
редактор показывает состояние ожидания.
В текущих сборках на узком экране длинный черновик можно прокручивать вверх и вниз внутри редактора.

Каждый чат автоматически сохраняет свой черновик локально. При переключении
чатов, изменении размера окна, переименовании и перезапуске восстанавливается
сохранённый текст на любом языке, включая пробелы и переносы строк. Черновики
отделены от истории сообщений. Они не передаются в контекст и не расходуют
токены или деньги.

Когда Tokenlogue добавляет ваше сообщение в переписку и начинает отправку,
отправленный черновик очищается. Ответ может прийти позже. Если вы начнёте
новый черновик, завершение предыдущего запроса его не сотрёт. Если проверка
перед отправкой завершится ошибкой или вы отмените платный запрос, исходный
черновик останется в поле ввода.

Отправка передаёт сообщение и контекст переписки в OpenRouter. Поэтому длинная
история влияет и на объём входных данных, и на бюджет следующего запроса.
Ответ или состояние запроса отображается в переписке.

<a name="ru-limits"></a>

### Как работают лимиты токенов и расходов

Настройте лимиты до первой отправки. В Tokenlogue различаются следующие параметры:

| Параметр | Значение |
| --- | --- |
| `Общий лимит токенов чата` | Общий бюджет входных и выходных токенов всех запросов чата. |
| `Максимум токенов одного ответа` | Максимум выходных токенов, запрашиваемых для следующего ответа. |
| `Денежный лимит чата, USD` | Локальный предел расходов платного чата. |

Общий бюджет учитывает и контекст переписки, который повторно передаётся
со следующими сообщениями. Максимум ответа задаёт верхнюю границу.
Сам ответ может быть короче. До отправки Tokenlogue резервирует токены, а
в платном чате также деньги. Если доступного бюджета недостаточно для резерва,
запрос может быть отклонён.

Откройте `⋮`, чтобы узнать, сколько бюджета использовано, зарезервировано
и осталось. Резерв удерживается для запросов, которые ещё выполняются или
имеют неизвестный результат. Пока резерв не освобождён, его нельзя использовать
для нового запроса. Неизвестный расход не считается нулевым. Резерв ограничивает
доступный бюджет в приложении и сам по себе не списывает деньги с учётной записи
OpenRouter. Фактические списания проверяйте в этой учётной записи.

Перед каждым платным запросом показывается подтверждение с моделью и
предварительным резервом. При изменении цен требуется ещё одно подтверждение.
Увеличение денежного лимита чата также требует подтверждения. Если отменить диалог, запрос не будет отправлен или прежний лимит останется
без изменений.

#### Если результат запроса неизвестен

Если соединение прервалось после возможного получения запроса OpenRouter,
Tokenlogue сохраняет защитный резерв. В переписке появляется сообщение
о неизвестном результате. Сервис мог обработать и тарифицировать запрос.

Перед повторной отправкой проверьте запрос и расход в своём аккаунте OpenRouter.
После проверки можно нажать `Освободить резерв` и подтвердить действие,
если вы хотите снова использовать эту часть бюджета. Оно снимает локальный резерв, но не отменяет
удалённый запрос и не возвращает списанные средства. Повторная отправка
может привести к ещё одному списанию.

<a name="ru-data"></a>

### Хранение данных и защита доступа

В опубликованной сборке для Linux `2b1f7d3` чаты, сообщения, черновики,
состояние бюджета и проверочные данные PIN хранятся в локальной базе
приложения без дополнительного шифрования содержимого. PIN не хранится открытым текстом, но ограничивает только доступ
через интерфейс Tokenlogue. Человек с доступом к вашей учётной записи ОС
или файлам базы может прочитать историю и черновики.

API-ключ и идентификатор регистрации хранятся отдельно в платформенном
SecureStorage. В Linux для этого нужен работающий Secret Service.
Сброс ключа сохраняет чаты и черновики, а удаление чата стирает его локальное
содержимое. Оба действия не удаляют записи у OpenRouter или поставщика
модели. Замена файла AppImage не удаляет данные приложения.


#### Защита локального содержимого в текущих сборках

Текущие сборки шифруют сохранённые названия чатов, сообщения пользователя
и модели, а также черновики. Ключ шифрования создаётся случайно и хранится
отдельно в платформенном защищённом хранилище. Он не выводится из
четырёхзначного PIN приложения или ключа OpenRouter. PIN управляет доступом
к этому ключу через Tokenlogue. В Linux нужен работающий Secret Service.
Если защищённое хранилище или ключ шифрования недоступны, приложение оставляет
переписку закрытой и не сохраняет её содержимое без защиты.

При первом успешном входе после обновления прежних локальных данных
Tokenlogue защищает существующее содержимое до открытия рабочего
пространства. История, черновики и их ревизии, ID чатов, выбор моделей
и финансовый учёт сохраняются. Если преобразование не удалось завершить,
приложение сообщает об ошибке и сохраняет данные. Не удаляйте базу и
не сбрасывайте защиту устройства, чтобы убрать это сообщение.

Если временная ошибка защищённого хранилища прервала первоначальную настройку
защиты, после восстановления хранилища повторите вход с прежним PIN приложения.
Tokenlogue может завершить подтверждённую незавершённую настройку с сохранением
данных. Это не создаёт заново потерянный ключ уже зашифрованной переписки.

В Linux перед первым входом с защитой переписки закройте все прежние копии
Tokenlogue, использующие этот каталог данных. Оставьте их закрытыми во время
преобразования и работы с обновлённым приложением. Текущие сборки допускают один
процесс на каталог данных и предлагают второй копии закрыть другую.
Прежние версии это правило не соблюдают.

Шифруются отдельные поля содержимого. Структурные сведения остаются
читаемыми, включая даты, ID моделей, режимы чатов, количество токенов,
бюджеты и состояния учёта. Это не шифрование всей базы SQLite и не сквозное
шифрование с OpenRouter. При отправке нужные сообщения и контекст по-прежнему
передаются в OpenRouter и выбранному поставщику модели.

Блокировка очищает видимое рабочее пространство и закрывает новый доступ.
Уже отправленный запрос может завершиться и сохранить ответ и учёт расходов
в защищённом виде. Это не гарантирует мгновенного удаления каждой копии
открытого текста и ключа из памяти работающего процесса. Защита не рассчитана
на уже скомпрометированную операционную систему.

После преобразования защита относится к текущим доступным файлам приложения.
Прежние внешние копии и ранее записанные блоки flash или SSD могут сохранять
старое содержимое. Резервное копирование приложения в Android остаётся
отключённым. Копирование базы на другое устройство не переносит защищённый
ключ. Удаление приложения, сброс его данных, потеря защищённого хранилища
или признание ключей Android Keystore недействительными могут сделать
переписку невосстановимой.
Изменение защиты устройства на некоторых устройствах влияет на доступность
ключа. Новый PIN приложения или API-ключ не создают заново потерянный
ключ шифрования.

Tokenlogue разрабатывается независимо от OpenRouter.
Перед отправкой личных сведений ознакомьтесь с условиями обработки данных
сервиса и поставщика модели.

[К Tokenlogue](../README.md#lang-ru)
