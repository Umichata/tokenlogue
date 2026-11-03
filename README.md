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

### Builds from the current source

Builds made from the current source offer `Русский / English` before sign-in.
After sign-in, use `Interface language` in `⋮`. Your choice is remembered.
Switching language keeps your typed PIN, draft and open dialog. Your messages
and chat titles stay in their original language.
While issuing a recovery code or recovering a PIN on Linux, changing language
cancels the unfinished attempt. It also closes an unconfirmed profile-deletion
dialog on either platform. Start again in the selected language.

The button at the top left hides or shows the chat list in a wide window
and opens it as a drawer in a narrow window. Hiding the wide panel gives
the conversation and editor more space. The wide-window choice is remembered
after locking, restarting or resizing the app.
See [language and chat panel controls](docs/user-guide.md#en-workspace).

After checking your OpenRouter key, choose a PIN. With English selected,
enter four digits from `0` to `9` in `PIN` and repeat them in `Repeat PIN`.
Leading zeros are allowed. `Suggest PIN` suggests a value that you can edit.
Save your chosen PIN with `Save PIN`.
Changing or generating the PIN clears its repeat field. The eye button lets
you reveal the value. It is never copied to the clipboard automatically.

Three incorrect app PIN checks lock PIN entry for five minutes. The same limit
applies when confirming your PIN before creating a recovery code. The countdown
continues across restarts, backgrounding and sleep. Recovery and local profile
deletion remain available during a PIN lockout.

After signing in, open `⋮` and choose `Replace OpenRouter key` to change any
saved API key, including a valid one. You can cancel the confirmation and keep
using the current key. Replacement keeps your app PIN and conversations.
Key replacement is available only after sign-in. The PIN screen offers
`Sign in`, `Delete local profile` and `Forgot PIN?` in that order.
Opening recovery does not change your PIN. A system lock or sleep cancels
an unfinished change. Your old PIN works until the new PIN is saved.

In a paid chat, enable `Without confirmation` in the compact strip above
the conversation, even before your first message, if you want requests to be sent
immediately within the chat's current limits. It is off by default for every
chat. When enabled, the first request, later requests and retries do not ask
for paid-request or price-change confirmation. Limits and real errors still
apply. Increasing the spending limit still needs confirmation.
The choice belongs to this chat and survives locking, restart and language
changes. Turn it off to restore confirmation for the next request.
See [paid chat settings](docs/user-guide.md#en-paid-confirmation).

The strip shows the remaining chat budget and the last sent request's actual
usage. Paid chats also show the current API key's remaining spending limit.
An exhausted limit, no separate limit and unavailable key data have distinct
labels. These values are separate from the OpenRouter account balance.
Under the editor, a local estimate updates as you type, including history
and the response maximum. It sends nothing and reserves no funds.
See [chat metrics and estimates](docs/user-guide.md#en-chat-metrics).

On Android, moving the app to the background locks access to chats. Returning
to the app requires your PIN. The selected chat, history and draft are kept.
An update preserves your existing PIN and does not require resetting access.
See [setup and locking in current builds](docs/user-guide.md#en-current).
These changes are not included in the published Linux preview `2b1f7d3`.

On supported Cinnamon/X11 systems, current builds lock with the screen,
when switching sessions and before sleep.
After a system lock or sleep, enter your app PIN again. Minimizing the window,
changing focus and copying text do not count as a system lock.

The compact shield opens `Local protection` in a separate scrollable panel.
It sits at the far right of the PIN screen's app header and beside `⋮` in chat.
Viewing protection leaves your PIN, draft and locked conversations untouched.
Screen locking and sleep have independent results with the time of the last
completed check. Results belong to this device and OS account. Restart, reboot
and normal sleep preserve them. Current monitoring is checked separately.
A connection by itself is not a successful protection check.

On Linux, saving a new protected profile automatically opens `Check local
protection`. Your key and PIN are already saved. `Start check` prepares the
screen locker and then asks the OS to lock. Nothing locks automatically just
because you saved your PIN. You do not need a previous manual OS lock.
Unlock the OS normally, then enter your saved app PIN. The result of that
same check appears automatically. An unfinished setup step resumes after
PIN sign-in if you restart. Replacing an existing key does not repeat setup.

From the locked PIN screen, choose a test in the protection panel and sign in
with your normal app PIN. The selected test reopens with `Start test`.
Only that explicit action requests an OS lock or sleep. Cancel or close the
panel to abandon the choice. Normal sign-in never starts an OS action.

After sign-in, `Test screen lock` is also available from the details,
including an empty chat list and a newly started desktop session. A confirmed
screen result does not confirm sleep. `Test sleep protection` saves your draft
and asks the computer to sleep only when you press it. Wake the computer,
unlock the OS normally and enter your app PIN. Neither test erases the other.
An uncertain or denied attempt leaves previous history intact. A proven
failure is red. `Continue with manual locking` lets you use the profile
without a confirmed check.

During reconnect, the previous result stays visible with a monitoring warning.
After compatible monitoring is restored, its confirmation returns without
another manual test. Changed protection requirements can require a new check.
History is kept outside the chat profile and is not transferred by copying
preferences or exporting conversations. A save error is shown explicitly.
Current Windows builds are not provided. Android keeps its existing background
lock and has no desktop setup step or test buttons.
See [local protection checks](docs/user-guide.md#en-protection-check).

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
can be used, with supported biometrics as an alternative.

On Linux, current builds offer a recovery code after PIN setup. You can also
sign in, open `⋮`, choose `Recovery code` and enter your app PIN again to issue
or replace it. Save the code separately in a password manager or on paper,
then confirm it by entering the saved code. It is shown only on that screen.
Anyone who has it can replace your PIN. The previous working code remains
valid until a replacement is confirmed.

`Forgot PIN?` on Linux opens code entry. A previously saved code lets you set
a new PIN without administrator rights, system policy or your Linux password.
The code is used once. After saving the new PIN, save and confirm a new code.
If you close that screen, the new PIN still works and you can issue another
code after signing in. Optional system recovery through polkit remains a
separate, explicitly selected method with its own setup.

If no code was issued before the PIN was forgotten, this update cannot create
one for the locked profile. You need the previous app PIN or an existing
working trusted recovery method. Your data stays in place.
See [Linux recovery](docs/linux-appimage.md#en-current-protection).

If you choose to give up the old local conversations, current Linux and Android
builds offer `Delete local profile` at the bottom of `⋮` after sign-in. It is
available even without a selected chat. You can also use it on the PIN screen
without the forgotten PIN.
Read the separate confirmation, type `DELETE PROFILE` and choose
`Delete profile`. This removes the local API key, PIN, recovery
code, encryption key, chats, drafts and local accounting. It does not open or
recover the old conversations. Anyone with access to that screen can confirm
deletion. External backups and exports stay in place. The action does not revoke
the key at OpenRouter or cancel remote requests and charges.
On the PIN screen, deletion appears above `Forgot PIN?`. For a supported
existing Linux data folder, the same confirmation also allows Tokenlogue to
make that folder private before checking and deleting the profile. Cancelling
the dialog changes nothing. A failure before data deletion says that deletion
has not started. It also explains if the folder was already made private.
No administrator rights or manual permission changes are needed.
See [deleting a local profile](docs/user-guide.md#en-delete) before using it.

A new OpenRouter key cannot unlock old protected conversations. Recovery also
needs the original encryption key to remain available. See
[local protection and recovery](docs/user-guide.md#en-data).

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

### Сборки из текущих исходников

В сборках из текущих исходников до входа доступен переключатель
`Русский / English`. После входа откройте `Язык интерфейса` в `⋮`.
Выбор сохраняется. Смена языка не очищает введённый PIN и черновик
и не закрывает открытый диалог. Сообщения и названия чатов сохраняют свой язык.
При выдаче резервного кода или восстановлении PIN в Linux смена языка
отменяет незавершённую попытку. На обеих платформах она также закрывает
неподтверждённый диалог удаления профиля. Начните заново на выбранном языке.

Кнопка слева в шапке скрывает и показывает список чатов в широком окне
и открывает его как выдвижную панель в узком окне. При скрытой широкой панели
переписка и редактор занимают освободившееся место. Выбор для широкого окна
сохраняется после блокировки, перезапуска и изменения размеров приложения.
Подробнее в разделе [о языке и панели чатов](docs/user-guide.md#ru-workspace).

После проверки ключа OpenRouter можно выбрать собственный PIN. Введите четыре цифры от `0` до `9` в поле `PIN` и повторите
их в поле `Повторите PIN`. Начальные нули допустимы. Кнопка `Предложить PIN`
подставляет значение, которое можно изменить. Сохраните выбранный PIN
кнопкой `Сохранить PIN`. Изменение или генерация PIN
очищает поле повторного ввода. Кнопка с глазом позволяет показать значение.
Автоматического копирования в буфер обмена нет.

Три неверные проверки PIN приложения блокируют ввод на пять минут. Это же
ограничение действует при подтверждении PIN перед созданием резервного кода.
Отсчёт продолжается после перезапуска, перехода в фон и сна. Восстановление
и удаление локального профиля остаются доступными при блокировке PIN.

После входа откройте `⋮` и выберите `Заменить ключ OpenRouter`, чтобы сменить
любой сохранённый API-ключ, в том числе действительный. Можно отменить
подтверждение и продолжить работу с текущим ключом. Замена сохраняет PIN
приложения и переписку.
Замена ключа доступна только после входа. На экране PIN действия идут в порядке
`Войти`, `Удалить локальный профиль`, `Забыли PIN?`.
Открытие восстановления не меняет PIN. Системная блокировка или сон отменяют
незавершённую смену. Прежний PIN действует до сохранения нового.

В платном чате включите `Без подтверждений` в компактной полосе над
перепиской, в том числе до первого сообщения, если хотите отправлять запросы
сразу в пределах текущих лимитов этого чата. По умолчанию настройка выключена
для каждого чата. При включении первый запрос, следующие запросы и повторы
проходят без подтверждений платного запроса или изменения цены. Лимиты
и действительные ошибки сохраняются. Увеличение денежного лимита по-прежнему
требует подтверждения. Выбор относится к этому чату и сохраняется после
блокировки, перезапуска и смены языка. Снимите флажок, чтобы вернуть
подтверждение уже для следующего запроса.
Подробнее в [настройках платного чата](docs/user-guide.md#ru-paid-confirmation).

Полоса показывает остаток бюджета чата и фактический расход последней
отправки. В платных чатах также виден остаток расходного лимита текущего
API-ключа. Исчерпание, отсутствие отдельного лимита и недоступные данные
ключа имеют разные подписи. Эти значения отделены от баланса OpenRouter.
Под редактором локальная оценка обновляется во время ввода с учётом
истории и максимума ответа. Она ничего не отправляет и не резервирует.
Подробнее в [статистике и оценке](docs/user-guide.md#ru-chat-metrics).

В Android переход приложения в фон блокирует доступ к чатам. После возврата
нужно ввести PIN. Выбранный чат, история и черновик сохраняются. Обновление
сохраняет прежний PIN и не требует сброса доступа. Подробнее в разделе
[о настройке и блокировке текущих сборок](docs/user-guide.md#ru-current).
Эти изменения не входят в опубликованную сборку для Linux `2b1f7d3`.

В поддерживаемых системах Cinnamon/X11 текущие сборки блокируются вместе
с экраном, при смене сессии и перед сном. После системной блокировки или сна введите PIN
приложения заново. Сворачивание окна, смена фокуса и копирование текста
не считаются системной блокировкой.

Компактный щит открывает `Локальная защита` отдельной прокручиваемой панелью.
Он находится крайним справа в шапке экрана PIN и рядом с `⋮` в чате.
Просмотр защиты не меняет PIN, черновик и закрытую переписку.
Экран и сон имеют отдельные результаты со временем последней завершённой
проверки. Они относятся к этому устройству и учётной записи ОС. Перезапуск,
перезагрузка и обычный сон их сохраняют. Текущее наблюдение проверяется
отдельно. Само подключение не является успешной проверкой защиты.

В Linux после сохранения нового защищённого профиля автоматически
открывается `Проверка локальной защиты`. Ключ и PIN уже сохранены.
`Начать проверку` подготавливает экранную службу и запрашивает блокировку ОС.
Одно сохранение PIN не блокирует экран. Предварительная ручная блокировка
ОС не нужна. Разблокируйте ОС обычным способом и введите сохранённый PIN
приложения. Результат того же теста появится автоматически. Незавершённый
шаг возобновляется после входа по PIN при перезапуске. Замена существующего
ключа не повторяет первоначальную настройку.

На закрытом экране PIN выберите тест в панели защиты и войдите с обычным
PIN приложения. Выбранная проверка откроется с кнопкой `Начать тест`.
Только это явное действие запрашивает блокировку ОС или сон. Отмена
или закрытие панели отменяют выбор. Обычный вход не запускает действие ОС.

После входа `Тест блокировки` доступен и в подробностях, в том числе
при пустом списке чатов и в новой сессии рабочего стола. Подтверждённый
экран не подтверждает сон. `Тест перехода в сон` сохраняет черновик
и запрашивает сон только по нажатию. Пробудите компьютер, разблокируйте ОС
обычным способом и введите PIN приложения. Ни один тест не стирает другой.
Неясная попытка или отказ запроса сохраняют прежнюю историю. Доказанный
отказ отмечается красным. `Продолжить с ручной блокировкой` позволяет
использовать профиль без подтверждённой проверки.

При переподключении прежний результат виден с предупреждением о наблюдении.
После восстановления совместимого наблюдения подтверждение возвращается
без нового ручного теста. Изменившиеся требования защиты могут потребовать
новой проверки. История хранится вне профиля чатов и не переносится
копированием предпочтений или экспортом переписки. Ошибка сохранения
показывается явно. Сборки Windows сейчас не предоставляются. Android
сохраняет прежнюю блокировку при переходе в фон без desktop-шага настройки
и кнопок тестов.
Подробнее в [проверках локальной защиты](docs/user-guide.md#ru-protection-check).

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
поддерживаемую биометрию.

В Linux текущие сборки предлагают резервный код после настройки PIN.
Также можно войти, открыть `⋮`, выбрать `Резервный код` и повторно ввести
PIN приложения для выдачи или перевыпуска. Сохраните код отдельно в менеджере
паролей или на бумаге, затем подтвердите его повторным вводом. Он показывается
только на этом экране. Обладающий кодом сможет заменить PIN. Прежний действующий
код сохраняется до подтверждения замены.

Кнопка `Забыли PIN?` в Linux открывает ввод кода. Заранее сохранённый код
позволяет назначить новый PIN без прав администратора, системной policy
и пароля Linux. Код используется один раз. После сохранения нового PIN
сохраните и подтвердите новый код. Если закрыть этот экран, новый PIN
продолжит работать. После входа можно выпустить другой код. Дополнительное
системное восстановление через polkit остаётся отдельным явно выбранным
способом со своей настройкой.

Если до потери PIN код не выдавался, обновление не может создать его для
закрытого профиля. Нужен прежний PIN приложения либо уже действующий
доверенный способ восстановления. Данные остаются на месте.
Подробнее в разделе [о восстановлении Linux](docs/linux-appimage.md#ru-current-protection).

Если вы решили отказаться от прежней локальной переписки, в текущих сборках
Linux и Android внизу `⋮` после входа есть `Удалить локальный профиль`.
Действие доступно и без выбранного чата. Его также можно использовать
на экране PIN без забытого PIN.
Прочитайте отдельное подтверждение, введите `УДАЛИТЬ ПРОФИЛЬ` и нажмите
`Удалить профиль`. Будут удалены локальные API-ключ, PIN,
резервный код, ключ шифрования, чаты, черновики и локальный учёт.
Прежняя переписка не открывается и не восстанавливается. Подтвердить удаление
сможет любой с доступом к этому экрану. Внешние резервные копии и экспорты
сохраняются. Действие не отзывает ключ в OpenRouter и не отменяет удалённые
запросы или списания. Перед использованием прочитайте раздел
[об удалении локального профиля](docs/user-guide.md#ru-delete).
На экране PIN удаление расположено выше `Забыли PIN?`. Для поддерживаемого
существующего каталога Linux это же подтверждение разрешает Tokenlogue
ограничить доступ к каталогу перед повторной проверкой и удалением профиля.
Отмена диалога ничего не меняет. Отказ до удаления данных сообщает, что
удаление не началось, и объясняет, если доступ к каталогу уже ограничен.
Права администратора и ручное изменение разрешений не нужны.

Новый ключ OpenRouter не открывает старую защищённую переписку.
Для восстановления также нужен сохранившийся ключ шифрования.
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
