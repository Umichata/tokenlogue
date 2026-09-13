# Tokenlogue - User guide / Руководство пользователя

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This guide describes the `0.1.0` preview `1472c00`. The interface is in
Russian. Russian labels below identify the controls you will see in the app.
For installation, use the [Linux AppImage guide](linux-appimage.md#lang-en).

[Key and PIN](#en-access) | [Chats and menu](#en-chats) |
[Messages and drafts](#en-drafts) | [Limits](#en-limits) | [Data](#en-data)

<a name="en-access"></a>

### First launch and signing in

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

Chats, messages, drafts, budget state and PIN verification data are stored
in the local application database. The database contents have no additional
encryption. The PIN is not stored as plain text, but it only restricts access
through Tokenlogue's interface. Someone with access to your OS account or
database files may be able to read the history and drafts.

The API key and registration identifier are stored separately in platform
SecureStorage. On Linux this requires a working Secret Service.
Resetting the key preserves chats and drafts, while deleting a chat removes
that chat's local content. Neither action deletes records held by OpenRouter
or a model provider. Replacing the AppImage file does not remove application data.

Tokenlogue is a client of the separate OpenRouter service and is not affiliated
with it. Review the service's and model provider's data terms before sending
private content.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Руководство описывает предварительную сборку `0.1.0` версии `1472c00`.
Интерфейс на русском языке. Ниже используются названия элементов, которые
видны в приложении. Установка описана в
[руководстве по AppImage для Linux](linux-appimage.md#lang-ru).

[Ключ и PIN](#ru-access) | [Чаты и меню](#ru-chats) |
[Сообщения и черновики](#ru-drafts) | [Лимиты](#ru-limits) | [Данные](#ru-data)

<a name="ru-access"></a>

### Первый запуск и вход в приложение

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

Чаты, сообщения, черновики, состояние бюджета и проверочные данные PIN
хранятся в локальной базе приложения. Дополнительного шифрования содержимого
базы нет. PIN не хранится открытым текстом, но ограничивает только доступ
через интерфейс Tokenlogue. Человек с доступом к вашей учётной записи ОС
или файлам базы может прочитать историю и черновики.

API-ключ и идентификатор регистрации хранятся отдельно в платформенном
SecureStorage. В Linux для этого нужен работающий Secret Service.
Сброс ключа сохраняет чаты и черновики, а удаление чата стирает его локальное
содержимое. Оба действия не удаляют записи у OpenRouter или поставщика
модели. Замена файла AppImage не удаляет данные приложения.

Tokenlogue разрабатывается независимо от OpenRouter.
Перед отправкой личных сведений ознакомьтесь с условиями обработки данных
сервиса и поставщика модели.

[К Tokenlogue](../README.md#lang-ru)
