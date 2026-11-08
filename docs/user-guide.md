# Using Tokenlogue / Работа с Tokenlogue

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

Tokenlogue lets you chat with OpenRouter models on Linux and Android. This guide describes the current preview. Earlier published previews can have fewer features. Start with the [Linux installation guide](linux-appimage.md#english) or [Android installation guide](android.md#english).

[Get started](#en-access) · [Chats](#en-chats) · [Drafts](#en-drafts) · [Limits](#en-limits) · [Costs](#en-chat-metrics) · [Protection](security.md#english)

<a id="en-access"></a>
<a id="en-current"></a>

### Get started

1. Choose English or Russian on the sign-in screen.
2. Enter an API key created in your [OpenRouter account](https://openrouter.ai/settings/keys) and choose `Check key`. This contacts OpenRouter. A connection error alone does not mean that the key is invalid.
3. Choose a four-digit PIN, repeat it and select `Save PIN`. Use digits `0`–`9`. A leading zero is allowed. `Suggest PIN` fills a random suggestion that you can change. Both fields must match before saving.
4. Keep the PIN somewhere safe. The eye button reveals it when needed. Tokenlogue does not copy it automatically.
5. On Linux, follow the local-protection introduction and save a recovery code when offered. You can choose to continue with manual app locking and check automatic protection later. See [protecting your conversations](security.md#en-locking).
6. Choose `+` to create a chat.

At later launches, enter your app PIN and choose `Sign in`. Updating a compatible installation preserves that PIN. Three incorrect checks temporarily block PIN entry for five minutes. Restarting does not clear the countdown. See [access and recovery](security.md#en-pin).

<a id="en-chats"></a>

### Create and manage chats

Choose free or paid mode, search by model name or ID, then set the chat limits. Each chat keeps its mode and model. Create another chat to choose a different model.

Free mode includes automatic model selection and models whose applicable prices are all zero. Automatic selection lets OpenRouter choose the model for each request. Free availability and service request limits still apply. Paid mode needs a valid key and known model prices. OpenRouter checks account funds when processing requests.

Use the chat list to return to a conversation. `Rename` and `Delete chat` sit below its title when there is enough vertical space. Renaming preserves messages and the draft. Deletion asks for confirmation and removes that chat's local history and draft. It does not delete the whole profile. These actions and limit editing are unavailable while sending.

The `⋮` menu contains key status, model details, token prices, budget details and limit settings. It also provides language selection, key replacement and profile actions. Opening the menu does not send a message or automatically refresh the key. Scroll inside the menu if it does not fit.

<a id="en-workspace"></a>

### Arrange the workspace

The top-left button hides or shows the chat list in a wide Linux window. Tokenlogue remembers that choice. On a narrow screen it opens a drawer. Choose a chat, tap outside, or use Back or Escape to close the drawer. Changing to a narrow layout does not overwrite the saved wide-window choice.

Choose `Interface language` in `⋮` to switch between English and Russian. The choice is remembered. Chat titles, your messages and model replies are not translated. Changing language preserves ordinary editor input and drafts. For safety, an unfinished recovery-code or profile-deletion confirmation must be started again in the selected language.

Long titles are shortened visually. When the keyboard or a short window leaves little room, the rename and delete shortcuts are hidden. Dismiss the keyboard or make the window taller to show them again. The conversation and editor use the remaining space.

<a id="en-drafts"></a>

### Send messages and keep drafts

Type in `Message` and choose `Send`. With a keyboard, Enter sends and Shift+Enter inserts a line break. Empty messages cannot be sent. Tokenlogue sends the message and eligible conversation context to OpenRouter and the selected model provider.

Each chat saves its own draft locally. Switching chats, resizing, renaming, locking and restarting preserve the saved text. A draft is separate from message history. Typing does not send it, spend funds or add it to model context.

Once a message is accepted for sending, its submitted draft is cleared. You can start a new draft while waiting. Completion of the previous request will not erase the newer text. A failed pre-send check or cancelled paid confirmation keeps the original draft.

If a reply is incomplete or a request fails, read its status before retrying. Retrying a request that already reached the service can cause another charge.

<a id="en-limits"></a>

### Set chat limits

Configure limits before the first request. Use `Set limits` or `Edit limits` in `⋮` to change them later.

| Setting | What it controls |
| --- | --- |
| Total chat token limit | Input and response tokens across this chat's requests. Repeated conversation context also uses tokens. |
| Maximum tokens per response | The requested upper bound for each answer. An answer can be shorter. |
| Chat spending limit, USD | The local spending cap for a paid chat. Increasing it asks for confirmation. |

Before sending, Tokenlogue reserves tokens and, in paid mode, money. The available chat budget excludes actual use and active reservations. A request can be refused when the remaining budget cannot cover its reserve. A local reservation is not an OpenRouter charge.

The chat budget, the spending limit of your OpenRouter key and your OpenRouter account balance are separate. Tokenlogue does not fetch the total account balance. A key without its own spending limit does not imply unlimited account funds.

<a id="en-paid-confirmation"></a>

### Choose when paid requests need confirmation

New paid chats ask for confirmation before sending. Review the model, estimated input, response maximum and spending reserve. Cancel to leave the message unsent.

`Without confirmation` above the conversation turns off that dialog for the selected chat, including its first request, retries and changed prices. Enabling it sends nothing by itself. Limits, key checks and price checks still apply. Raising the spending limit keeps its separate confirmation.

Turn the option off to require confirmation from the next request onward. The choice is saved per chat. Locking or changing this setting never submits a queued message automatically. Choose `Send` when ready.

<a id="en-chat-metrics"></a>

### Read token and cost information

| Display | Meaning |
| --- | --- |
| Chat available | Paid-chat budget remaining after actual costs and active reservations. |
| Tokens remaining | Free-chat token budget remaining after use and active reservations. This is not OpenRouter's global free quota. |
| Last request | Confirmed cost for a paid chat or total input-and-response tokens for a free chat. Retries count as new attempts. |
| Key remaining | The current API key's known remaining spending limit, separate from the chat budget and account balance. |

`Key limit not set` means that the key has no separate cap. `Key data unavailable` means its remainder is unknown. An exhausted limit is shown explicitly. Hover or long-press a metric for details and the key-data receipt time when available. Use `Refresh key status` in `⋮` to request fresh data. Typing or reopening the display does not make old data fresh.

`No requests`, `In progress`, `Reconciling` and `Unknown` describe different states. An unknown result is not treated as zero cost.

The estimate under the editor changes as you type. It includes eligible history and the effective response maximum. It is a conservative local estimate based on UTF-8 text, not exact model tokenization or a prediction of reply length. The possible cost is an upper estimate for known prices. Missing or expired pricing produces `Cost unknown`. Actual usage and cost are determined after sending.

Calculating an estimate makes no network request and reserves no budget. The normal checks still run when you send.

### Handle an unknown request result

A lost connection can leave uncertainty about whether OpenRouter processed a request. Tokenlogue keeps its protective reserve rather than treating it as free. Check the request and billing in your OpenRouter account before retrying.

After checking, `Release unknown reservation` returns that local reserve to the chat budget. It does not cancel a remote request or refund a charge. A retry can create another charge.

<a id="en-key-replacement"></a>

### Replace an OpenRouter key

Sign in with your existing PIN, open `⋮` and choose `Replace OpenRouter key`. This works with or without a selected chat. Finish any current send or key check first.

The old key stays saved until the replacement passes validation and is stored. Cancellation or a failed check keeps it. Your PIN, encryption key, chats, drafts and budgets stay the same. This action neither recovers a forgotten PIN nor revokes the old key at OpenRouter. Revoke a key in your OpenRouter account if needed.

<a id="en-protection-check"></a>
<a id="en-pin-recovery"></a>
<a id="en-delete"></a>
<a id="en-data"></a>

### Protect your conversations

Use the header lock button before leaving the device. On Android, moving the app to the background closes access. Linux screen-lock and sleep monitoring depends on the desktop session.

Read [conversation protection and recovery](security.md#english) before relying on a PIN or changing device security. It explains encrypted fields, the Linux recovery code, Android system recovery, local-protection checks and irreversible profile deletion. Copying a database alone does not back up its separate encryption key.

[Tokenlogue](../README.md#english) · [Linux](linux-appimage.md#english) · [Android](android.md#english) · [Source materials](source-materials.md#english)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Tokenlogue позволяет общаться с моделями OpenRouter в Linux и Android. Руководство описывает текущую предварительную версию. В прежних опубликованных выпусках возможностей может быть меньше. Начните с [установки в Linux](linux-appimage.md#russian) или [установки в Android](android.md#russian).

[Начало работы](#ru-access) · [Чаты](#ru-chats) · [Черновики](#ru-drafts) · [Лимиты](#ru-limits) · [Расходы](#ru-chat-metrics) · [Защита](security.md#russian)

<a id="ru-access"></a>
<a id="ru-current"></a>

### Начало работы

1. Выберите русский или английский язык на экране входа.
2. Введите API-ключ из своего [аккаунта OpenRouter](https://openrouter.ai/settings/keys) и нажмите `Проверить ключ`. Для этого нужен доступ к OpenRouter. Ошибка соединения сама по себе не означает, что ключ неверный.
3. Выберите четырёхзначный PIN, повторите его и нажмите `Сохранить PIN`. Используйте цифры `0`–`9`. Ноль в начале допустим. Кнопка `Предложить PIN` заполняет случайный вариант, который можно изменить. Для сохранения значения обоих полей должны совпадать.
4. Сохраните PIN в надёжном месте. Кнопка с глазом позволяет увидеть его. Tokenlogue не копирует PIN автоматически.
5. В Linux пройдите начальную проверку локальной защиты и сохраните резервный код, когда приложение предложит это. Можно продолжить с ручной блокировкой приложения и проверить автоматическую защиту позднее. Подробнее в разделе [о защите переписки](security.md#ru-locking).
6. Нажмите `+`, чтобы создать чат.

При следующих запусках введите PIN приложения и нажмите `Войти`. Обновление совместимой установки сохраняет этот PIN. После трёх неверных проверок ввод блокируется на пять минут. Перезапуск не сбрасывает отсчёт. Подробнее в разделе [о входе и восстановлении](security.md#ru-pin).

<a id="ru-chats"></a>

### Создание чатов и управление ими

Выберите бесплатный или платный режим, найдите модель по названию или ID и задайте лимиты чата. В каждом чате сохраняются его режим и модель. Для другой модели создайте новый чат.

В бесплатном режиме доступны автоматический выбор и модели, у которых все применимые цены равны нулю. При автоматическом выборе модель для каждого запроса определяет OpenRouter. Доступность и ограничения частоты бесплатных запросов сервиса сохраняются. Для платного режима нужны действующий ключ и известные цены модели. Наличие средств OpenRouter проверяет при обработке запросов.

Возвращайтесь к переписке через список чатов. Если хватает места по высоте, под заголовком находятся `Переименовать` и `Удалить чат`. Переименование сохраняет сообщения и черновик. Удаление требует подтверждения и удаляет локальную историю и черновик только этого чата. Весь профиль при этом сохраняется. Эти действия и изменение лимитов недоступны во время отправки.

В меню `⋮` находятся состояние ключа, сведения о модели, цены токенов, подробный бюджет и настройки лимитов. Здесь же доступны язык, замена ключа и действия с профилем. Открытие меню не отправляет сообщение и не обновляет ключ автоматически. Если пункты не помещаются, прокрутите меню.

<a id="ru-workspace"></a>

### Настройка рабочего пространства

В широком окне Linux верхняя левая кнопка скрывает или показывает список чатов. Tokenlogue запоминает выбор. На узком экране эта кнопка открывает выдвижную панель. Выберите чат, нажмите вне панели или используйте Back либо Escape, чтобы её закрыть. Узкая компоновка не меняет сохранённую настройку широкого окна.

Для переключения русского и английского выберите `Язык интерфейса` в `⋮`. Выбор сохраняется. Названия чатов, ваши сообщения и ответы модели не переводятся. Обычный ввод и черновики сохраняются при смене языка. Незавершённое подтверждение резервного кода или удаления профиля нужно начать заново на выбранном языке.

Длинные названия визуально сокращаются. Когда клавиатура или низкое окно оставляют мало места, кнопки переименования и удаления скрываются. Закройте клавиатуру или увеличьте высоту окна, чтобы они снова появились. Переписка и редактор используют оставшееся пространство.

<a id="ru-drafts"></a>

### Отправка сообщений и сохранение черновиков

Введите текст в поле `Сообщение` и нажмите `Отправить`. При работе с клавиатурой Enter отправляет сообщение, а Shift+Enter добавляет перенос строки. Пустые сообщения отправить нельзя. Tokenlogue передаёт сообщение и подходящий контекст переписки в OpenRouter и выбранному поставщику модели.

У каждого чата свой локальный черновик. Сохранённый текст восстанавливается после переключения чатов, изменения размера окна, переименования, блокировки и перезапуска. Черновик существует отдельно от истории. Ввод текста не отправляет его, не расходует средства и не добавляет в контекст модели.

Когда сообщение принято к отправке, отправленный черновик очищается. Пока ответ готовится, можно писать новый. Завершение прошлого запроса не удалит новый текст. Неудачная проверка до отправки или отменённое подтверждение платного запроса сохраняют исходный черновик.

Если ответ неполный или запрос завершился ошибкой, прочитайте его состояние перед повтором. Повтор запроса, уже дошедшего до сервиса, может привести к ещё одному списанию.

<a id="ru-limits"></a>

### Настройка лимитов чата

Задайте лимиты до первого запроса. Для изменения откройте `Настроить лимиты` или `Изменить лимиты` в `⋮`.

| Настройка | Что она ограничивает |
| --- | --- |
| Общий лимит токенов чата | Входные токены и ответы во всех запросах чата. Повторная передача контекста тоже расходует токены. |
| Максимум токенов одного ответа | Запрашиваемая верхняя граница ответа. Ответ может быть короче. |
| Денежный лимит чата, USD | Локальный предел расходов платного чата. Повышение требует подтверждения. |

Перед отправкой Tokenlogue резервирует токены, а в платном режиме ещё и деньги. Из доступного бюджета чата вычитаются фактический расход и действующие резервы. Если остатка недостаточно для нового резерва, запрос может быть отклонён. Локальный резерв не является списанием OpenRouter.

Бюджет чата, лимит расходов ключа OpenRouter и баланс аккаунта OpenRouter — разные величины. Tokenlogue не получает общий баланс аккаунта. Отсутствие отдельного лимита ключа не означает неограниченные средства.

<a id="ru-paid-confirmation"></a>

### Подтверждение платных запросов

В новых платных чатах перед отправкой появляется подтверждение. Проверьте модель, оценку входа, максимум ответа и денежный резерв. Отмена оставляет сообщение неотправленным.

Пункт `Без подтверждений` над перепиской отключает этот диалог для выбранного чата с первого запроса, включая повторы и изменение цен. Само включение ничего не отправляет. Лимиты, проверка ключа и проверка цен продолжают действовать. Повышение денежного лимита сохраняет отдельное подтверждение.

Отключите этот пункт, чтобы запрашивать подтверждение начиная со следующего запроса. Выбор сохраняется для каждого чата. Блокировка или изменение настройки никогда не отправляют ожидающее сообщение автоматически. Нажмите `Отправить`, когда будете готовы.

<a id="ru-chat-metrics"></a>

### Как читать статистику и оценку расходов

| Показатель | Значение |
| --- | --- |
| В чате доступно | Остаток бюджета платного чата после фактических расходов и действующих резервов. |
| Осталось токенов | Остаток токенов бесплатного чата после расхода и действующих резервов. Это не общая бесплатная квота OpenRouter. |
| Последний запрос | Подтверждённая стоимость в платном чате или сумма входных токенов и ответа в бесплатном. Повтор считается новой попыткой. |
| Осталось по ключу | Известный остаток лимита расходов текущего API-ключа. Он отличается от бюджета чата и баланса аккаунта. |

`Лимит ключа не установлен` означает отсутствие отдельного ограничения ключа. `Данные ключа недоступны` означает неизвестный остаток. Исчерпанный лимит обозначается отдельно. Наведите указатель или удерживайте показатель для пояснения и времени получения данных ключа, если оно известно. Пункт `Обновить статус ключа` в `⋮` запрашивает свежие данные. Ввод текста или повторное открытие показателей не обновляет старые сведения.

Состояния `Нет запросов`, `Выполняется`, `Уточняется` и `Неизвестно` различаются. Неизвестный результат не считается нулевой стоимостью.

Оценка под редактором меняется во время ввода. Она учитывает подходящую историю и действующий максимум ответа. Это консервативная локальная оценка на основе текста UTF-8, а не точная токенизация модели и не прогноз длины ответа. Возможная стоимость является верхней оценкой при известных ценах. При отсутствующих или устаревших ценах показывается `Стоимость неизвестна`. Фактические токены и стоимость определяются после отправки.

Расчёт оценки не обращается к сети и не резервирует бюджет. При отправке выполняются обычные проверки.

### Если результат запроса неизвестен

После потери соединения может быть неизвестно, обработал ли OpenRouter запрос. Tokenlogue сохраняет защитный резерв, а не считает запрос бесплатным. Перед повтором проверьте запрос и списания в аккаунте OpenRouter.

После проверки пункт `Освободить неизвестный резерв` возвращает локальный резерв в бюджет чата. Он не отменяет удалённый запрос и не возвращает оплату. Повтор может привести к новому списанию.

<a id="ru-key-replacement"></a>

### Замена ключа OpenRouter

Войдите с прежним PIN, откройте `⋮` и выберите `Заменить ключ OpenRouter`. Это доступно и без выбранного чата. Сначала завершите текущую отправку или проверку ключа.

Старый ключ сохраняется, пока новый не пройдёт проверку и не будет записан. Отмена или неудачная проверка оставляют его. PIN, ключ шифрования, чаты, черновики и бюджеты не меняются. Это действие не восстанавливает забытый PIN и не отзывает старый ключ на стороне OpenRouter. При необходимости отзовите ключ в аккаунте OpenRouter.

<a id="ru-protection-check"></a>
<a id="ru-pin-recovery"></a>
<a id="ru-delete"></a>
<a id="ru-data"></a>

### Защита переписки

Перед тем как оставить устройство, используйте кнопку блокировки в шапке. В Android уход приложения в фон закрывает доступ. В Linux наблюдение за блокировкой экрана и сном зависит от рабочего окружения.

Прочитайте [руководство по защите и восстановлению](security.md#russian), прежде чем полагаться на PIN или менять защиту устройства. Оно объясняет шифруемые поля, резервный код Linux, системное восстановление Android, проверку локальной защиты и необратимое удаление профиля. Копия базы сама по себе не сохраняет отдельный ключ шифрования.

[Tokenlogue](../README.md#russian) · [Linux](linux-appimage.md#russian) · [Android](android.md#russian) · [Исходные материалы](source-materials.md#russian)
