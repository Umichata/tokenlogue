# Conversation protection / Защита переписки

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

Tokenlogue protects access to locally stored conversations with an app PIN and a separate encryption key. This guide covers the current Linux and Android preview. Earlier published versions can store conversation content without this protection.

[PIN](#en-pin) · [Locking](#en-locking) · [Recovery](#en-recovery) · [Encryption](#en-encryption) · [Delete a profile](#en-delete)

<a id="en-pin"></a>

### Your app PIN

Choose four digits `0`–`9` and repeat them during setup. A leading zero is allowed. Save the PIN separately. The eye button can reveal it, but Tokenlogue never copies it automatically.

Three incorrect PIN checks block PIN entry for five minutes. Sign-in and PIN confirmation before issuing a recovery code share this limit. Restarting, sleeping or changing language does not reset it. Wait for the displayed countdown to finish. Recovery and local profile deletion remain available.

The app PIN is different from your Linux password and Android screen-lock PIN. It controls access through Tokenlogue. It is not the encryption key and is not a substitute for a protected OS account.

<a id="en-locking"></a>

### Lock the app when you leave

Use the lock button in the header to close access to chats. Returning requires the app PIN. Locking saves the latest draft. A request already sent can still finish and record its response and cost. The app does not automatically send a draft when you return.

On Android, leaving the app for the background locks access and closes dialogs. Returning to the app or unlocking Android does not unlock Tokenlogue. Merely opening the keyboard or briefly losing focus is not the same as backgrounding.

On Linux, screen-lock and sleep monitoring depends on the desktop. The supported Cinnamon/X11 session can close access on screen lock, session switching and suspend. Minimizing or changing focus alone does not lock the app. Use manual app locking whenever monitoring is unavailable or unconfirmed. Other desktops, Wayland, additional displays and ambiguous sessions can limit automatic detection.

### Check Linux screen-lock and sleep protection

After saving a new protected Linux profile, `Check local protection` explains the check before opening chats. Your PIN is already saved. Only `Start check` requests the system screen lock. Unlock Linux normally, then enter that app PIN. Choose `Open chats` after reviewing the result. If interrupted, sign in with your saved PIN to resume. You can choose `Continue with manual locking` and check again later.

The shield in the app header opens the protection panel before or after sign-in. Opening it never locks or suspends the computer. While signed out, choosing a test first takes you through normal app PIN sign-in. `Start test` remains a separate action.

`Test screen lock` saves the draft and requests a normal system lock. `Test sleep protection` saves it and asks the computer to sleep. For the latter, wake the computer, unlock Linux normally and enter the app PIN. You do not need a successful screen test before testing sleep. The two checks have separate results.

The panel distinguishes remembered checks from monitoring available now. A previous successful check is not proof that a currently disconnected service works. Results belong to this device and OS account. A different desktop setup may need another check. A cancelled or refused check does not confirm protection. Do not change system security settings merely to make a test succeed.

Android uses background locking and has no desktop screen-lock or sleep tests in this panel.

<a id="en-recovery"></a>

### Recover a forgotten app PIN

Recovery lets you choose and save a new app PIN. It needs an existing valid recovery method and the original protected encryption key. It cannot rebuild a lost key or restore a database from a code alone.

Opening `Forgot PIN?` does not change the PIN. Your previous PIN keeps working until a new one is saved. A system lock, backgrounding or language change can cancel an unfinished attempt. Start again if needed. A new PIN already saved remains active.

#### Linux recovery code

Save a code before you need it. After signing in, open `⋮` and choose `Recovery code`. Confirm your app PIN again. New profiles also offer this after the local-protection introduction.

The code has 32 Base32 characters, displayed in groups of four. Anyone with it can replace the app PIN. Save it separately in a password manager or on paper, then repeat the saved code to confirm. It is shown once. Copying is optional, and clipboard history may keep a copy.

A previous code remains valid until a replacement is confirmed. Cancelling or a failed save keeps the working code. You cannot reveal the same code later. Sign in and issue a replacement if you need a new one.

To use it, choose `Forgot PIN?`, enter the saved code, then choose, repeat and save a new app PIN. ASCII letter case, ordinary spaces and hyphens are accepted. All 32 characters are required. Five incorrect code checks block code entry for 30 seconds, separately from the app PIN limit. Restarting does not bypass the delay.

Saving the new PIN consumes the code. Save and confirm the replacement offered afterwards. If you close the app first, sign in with the new PIN and create another code from `⋮`.

Code recovery needs no Linux password, administrator rights or system policy. It keeps your API key, encryption key, conversations, drafts and budgets. It cannot be enrolled while a profile is already locked with a forgotten PIN. A new API key or an unlocked keyring does not prove access to that profile.

#### Optional Linux system recovery

`Use Linux system recovery` is a separate choice. It requests fresh confirmation of your own Linux account through the desktop authentication window. Enter your Linux password only in that system window, never into Tokenlogue. A different administrator account or an already unlocked keyring does not replace this check.

This option needs the separately installed Tokenlogue policy and a working desktop authentication agent. Without them, conversations stay closed. The [Linux guide](linux-appimage.md#en-system-recovery) explains the optional setup. Recovery codes work without it.

#### Android system recovery

On Android 11 or later, `Forgot PIN?` can request a separate system check of the device PIN, pattern or password. Supported biometrics may also be offered. A fingerprint is not required. A supported screen lock must be configured. Simply unlocking the device does not complete this fresh check.

After verification, choose a new app PIN, repeat it and select `Save new PIN`. Cancelling before saving keeps the previous PIN and conversations. If verification is unavailable or refused, use your existing app PIN. Android 7–10 can run the app but do not provide this recovery method.

<a id="en-encryption"></a>

### What is encrypted

Tokenlogue encrypts saved chat titles, user and model messages, and drafts. A random encryption key is stored separately in platform secure storage. It is not derived from the four-digit PIN or OpenRouter key. Linux needs an available, unlocked Secret Service such as GNOME Keyring.

Dates, model identifiers, chat modes, token counts, budgets and accounting states remain readable. This is encryption of selected database fields. It does not encrypt the whole database or device, and it is not end-to-end encryption with OpenRouter. Sending transmits the necessary messages and context to OpenRouter and the selected model provider. Check their data policies before sending private information.

If secure storage or the encryption key is unavailable, conversations stay closed. After a temporary storage failure, restore access to the system key store and retry the existing PIN. Do not delete the database or reset device security to dismiss the error.

When upgrading older local data, the first successful sign-in protects its content before opening chats. History, drafts, models and accounting are preserved. Close all older Linux copies first and keep them closed. Current builds allow one process per data folder, but earlier versions do not follow that rule.

Copying the database alone does not back up its encryption key. Android application backup is disabled. Uninstalling, clearing app data, losing secure storage or invalidating Android Keystore can make conversations unrecoverable. Changes to device security can affect key availability on some devices. A new PIN, recovery code or API key cannot recreate a lost encryption key.

Locking clears the visible workspace and closes new access. It does not promise immediate erasure of every plaintext or key copy from process memory. It cannot protect an already compromised operating system. Old external backups, storage blocks, swap or snapshots may retain earlier content.

<a id="en-delete"></a>

### Delete a local profile

**Deletion is irreversible within Tokenlogue.** To keep conversations, use a valid recovery method instead.

`Delete local profile` is available on the PIN screen and at the bottom of `⋮` after sign-in, even without a selected chat. It remains available during PIN lockout. It does not require the old PIN, a recovery code, Linux password or network access. Anyone who can use this screen can confirm it.

Read the dialog, type the displayed phrase `DELETE PROFILE` exactly, then choose `Delete profile`. `Keep profile` cancels before acceptance. The phrase confirms intent, not identity. Changing language or closing an unconfirmed dialog cancels it.

Deletion removes the profile's local API key, PIN, recovery code, encryption key, chats, messages, drafts, limits and spending records. The new profile cannot recover the old conversations. Language and panel layout choices remain. External exports and backups are untouched. Secure physical erasure of all device copies is not guaranteed.

On Linux, Tokenlogue may first make its own supported data folder private. A failure before deletion starts keeps the profile. If permissions were already restricted, the folder stays private. Do not manually remove files or change permissions to bypass an error.

Once deletion has begun, it must finish. If storage fails, chats stay closed. Use `Finish deletion` or restart to continue. New setup opens only after removal is complete. Enter a key and choose a new PIN for the empty profile.

Deleting locally does not revoke your key at OpenRouter, delete that account, cancel submitted requests or refund charges. Use `Replace OpenRouter key` after sign-in when you want to change keys and keep conversations.

[User guide](user-guide.md#english) · [Linux](linux-appimage.md#english) · [Android](android.md#english) · [Tokenlogue](../README.md#english)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Tokenlogue защищает доступ к локальной переписке PIN приложения и отдельным ключом шифрования. Это руководство относится к текущей предварительной версии для Linux и Android. Прежние опубликованные версии могут хранить переписку без этой защиты.

[PIN](#ru-pin) · [Блокировка](#ru-locking) · [Восстановление](#ru-recovery) · [Шифрование](#ru-encryption) · [Удаление профиля](#ru-delete)

<a id="ru-pin"></a>

### PIN приложения

При настройке выберите четыре цифры `0`–`9` и повторите их. Ноль в начале допустим. Сохраните PIN отдельно. Кнопка с глазом позволяет увидеть его, но Tokenlogue никогда не копирует его автоматически.

После трёх неверных проверок ввод PIN блокируется на пять минут. Вход и подтверждение PIN перед выдачей резервного кода используют общий предел. Перезапуск, сон и смена языка не сбрасывают его. Дождитесь окончания показанного отсчёта. Восстановление и удаление локального профиля остаются доступны.

PIN приложения отличается от пароля Linux и PIN блокировки Android. Он управляет доступом через Tokenlogue. Это не ключ шифрования и не замена защите учётной записи ОС.

<a id="ru-locking"></a>

### Блокировка перед уходом

Нажмите кнопку блокировки в шапке, чтобы закрыть доступ к чатам. Для возврата нужен PIN приложения. Последний черновик сохраняется. Уже отправленный запрос может завершиться и сохранить ответ и расходы. При возвращении приложение не отправляет черновик автоматически.

В Android уход приложения в фон закрывает доступ и диалоги. Возврат в приложение или разблокировка Android не открывают Tokenlogue. Появление клавиатуры или краткая потеря фокуса сами по себе не равны уходу в фон.

В Linux наблюдение за блокировкой и сном зависит от рабочего окружения. Поддерживаемая сессия Cinnamon/X11 позволяет закрывать доступ при блокировке экрана, переключении сессии и засыпании. Сворачивание или смена фокуса сами по себе не блокируют приложение. Используйте ручную блокировку, если наблюдение недоступно или не подтверждено. Другие рабочие окружения, Wayland, дополнительные дисплеи и неоднозначные сессии могут ограничивать автоматическое обнаружение.

### Проверка блокировки экрана и сна в Linux

После сохранения нового защищённого профиля Linux экран `Проверка локальной защиты` объясняет проверку до открытия чатов. Ваш PIN уже сохранён. Только кнопка `Начать проверку` запрашивает системную блокировку экрана. Разблокируйте Linux обычным способом и введите PIN приложения. После просмотра результата выберите `Перейти к чатам`. Если шаг прервался, войдите с сохранённым PIN, чтобы продолжить. Можно выбрать `Продолжить с ручной блокировкой` и проверить позднее.

Щит в шапке открывает панель защиты до или после входа. Само открытие не блокирует и не усыпляет компьютер. Если выбрать проверку до входа, сначала потребуется обычный PIN приложения. `Начать тест` остаётся отдельным действием.

`Тест блокировки` сохраняет черновик и запрашивает обычную системную блокировку. `Тест перехода в сон` сохраняет его и отправляет компьютер в сон. Во втором случае разбудите компьютер, разблокируйте Linux и введите PIN приложения. Для проверки сна не нужна предварительная успешная проверка экрана. Результаты двух проверок сохраняются отдельно.

Панель различает сохранённые результаты и наблюдение, доступное сейчас. Прежняя успешная проверка не доказывает работу временно недоступной службы. Результаты относятся к этому устройству и учётной записи ОС. Другая настройка рабочего окружения может потребовать новой проверки. Отмена или отказ не подтверждают защиту. Не меняйте системные настройки безопасности только ради успешного результата.

Android использует блокировку при уходе в фон. В его панели нет настольных проверок экрана или сна.

<a id="ru-recovery"></a>

### Восстановление забытого PIN

Восстановление позволяет выбрать и сохранить новый PIN приложения. Для него нужны ранее доступный действующий способ подтверждения и исходный защищённый ключ шифрования. Оно не воссоздаёт потерянный ключ и не восстанавливает базу по одному коду.

Открытие `Забыли PIN?` не меняет PIN. Прежний PIN работает, пока новый не сохранён. Системная блокировка, уход в фон или смена языка могут отменить незавершённую попытку. При необходимости начните заново. Уже сохранённый новый PIN остаётся действующим.

#### Резервный код Linux

Сохраните код заранее. После входа откройте `⋮` и выберите `Резервный код`. Ещё раз подтвердите PIN приложения. Новый профиль также предлагает это после начального шага локальной защиты.

Код содержит 32 символа Base32, показанных группами по четыре. Любой, у кого есть этот код, может заменить PIN приложения. Сохраните его отдельно в менеджере паролей или на бумаге, затем повторите сохранённый код для подтверждения. Он показывается один раз. Копирование необязательно, а история буфера обмена может сохранить копию.

Прежний код действует до подтверждения нового. Отмена или ошибка сохранения оставляют рабочий код. Повторно показать тот же код нельзя. Если нужен новый, войдите и выпустите замену.

Для использования выберите `Забыли PIN?`, введите сохранённый код, затем выберите, повторите и сохраните новый PIN. Регистр ASCII-букв, обычные пробелы и дефисы допустимы. Нужны все 32 символа. После пяти неверных проверок ввод кода блокируется на 30 секунд отдельно от ограничения PIN. Перезапуск не обходит задержку.

Сохранение нового PIN расходует использованный код. Сохраните и подтвердите предложенную замену. Если вы сначала закроете приложение, войдите с новым PIN и создайте другой код через `⋮`.

Для кода не нужны пароль Linux, права администратора или системная policy. Восстановление сохраняет API-ключ, ключ шифрования, переписку, черновики и бюджеты. Создать код для уже закрытого профиля с забытым PIN нельзя. Новый API-ключ или разблокированная связка ключей не подтверждают доступ к этому профилю.

#### Дополнительное системное восстановление Linux

`Системное восстановление Linux` выбирается отдельно. Оно запрашивает новое подтверждение вашей учётной записи Linux через системное окно. Вводите пароль Linux только в нём, никогда в Tokenlogue. Другой администратор или уже открытая связка ключей не заменяют проверку.

Для этого способа нужны отдельно установленная policy Tokenlogue и работающий системный агент аутентификации. Без них переписка остаётся закрытой. Необязательная настройка описана в [руководстве Linux](linux-appimage.md#ru-system-recovery). Резервный код работает без неё.

#### Системное восстановление Android

В Android 11 и новее `Забыли PIN?` может запросить отдельную системную проверку PIN, графического ключа или пароля устройства. Также могут предлагаться поддерживаемые биометрические способы. Отпечаток пальца не обязателен. Должна быть настроена поддерживаемая блокировка экрана. Обычная разблокировка устройства не заменяет эту новую проверку.

После подтверждения выберите новый PIN приложения, повторите его и нажмите `Сохранить новый PIN`. Отмена до сохранения оставляет прежний PIN и переписку. Если проверка недоступна или отклонена, используйте прежний PIN. В Android 7–10 приложение может работать, но этого способа восстановления нет.

<a id="ru-encryption"></a>

### Что шифруется

Tokenlogue шифрует сохранённые названия чатов, сообщения пользователя и модели, а также черновики. Случайный ключ шифрования находится отдельно в платформенном защищённом хранилище. Он не выводится из четырёхзначного PIN или ключа OpenRouter. В Linux нужен доступный и разблокированный Secret Service, например GNOME Keyring.

Даты, ID моделей, режимы чатов, число токенов, бюджеты и состояния учёта остаются читаемыми. Это шифрование отдельных полей базы. Оно не шифрует всю базу или устройство и не является сквозным шифрованием с OpenRouter. При отправке нужные сообщения и контекст передаются в OpenRouter и выбранному поставщику модели. Изучите их правила обработки данных перед передачей личных сведений.

Если защищённое хранилище или ключ шифрования недоступны, переписка остаётся закрытой. После временной ошибки восстановите доступ к системному хранилищу и повторите вход с прежним PIN. Не удаляйте базу и не сбрасывайте защиту устройства ради устранения сообщения.

При обновлении старых локальных данных первый успешный вход защищает содержимое до открытия чатов. История, черновики, модели и учёт сохраняются. Сначала закройте все прежние копии Linux и держите их закрытыми. Текущие сборки допускают один процесс на каталог данных, но прежние версии это правило не соблюдают.

Копия базы сама по себе не сохраняет ключ шифрования. Резервное копирование приложения в Android отключено. Удаление приложения, очистка данных, потеря защищённого хранилища или недействительность Android Keystore могут сделать переписку невосстановимой. На некоторых устройствах изменение системной защиты влияет на доступность ключей. Новый PIN, резервный код или API-ключ не воссоздают потерянный ключ шифрования.

Блокировка очищает видимое рабочее пространство и закрывает новый доступ. Она не обещает мгновенного удаления всех копий открытого текста и ключей из памяти процесса. Она не защищает уже скомпрометированную ОС. Старые внешние копии, блоки накопителя, swap или снимки системы могут хранить прежнее содержимое.

<a id="ru-delete"></a>

### Удаление локального профиля

**Удаление необратимо средствами Tokenlogue.** Для сохранения переписки используйте действующий способ восстановления.

`Удалить локальный профиль` доступно на экране PIN и внизу `⋮` после входа, в том числе без выбранного чата. Действие остаётся доступным при блокировке ввода PIN. Прежний PIN, резервный код, пароль Linux и сеть не требуются. Подтвердить удаление может любой, у кого есть доступ к этому экрану.

Прочитайте диалог, точно введите показанную фразу `УДАЛИТЬ ПРОФИЛЬ` и нажмите `Удалить профиль`. `Сохранить профиль` отменяет действие до принятия. Фраза подтверждает намерение, а не личность. Смена языка или закрытие неподтверждённого диалога отменяют его.

Удаляются локальные API-ключ, PIN, резервный код, ключ шифрования, чаты, сообщения, черновики, лимиты и записи расходов этого профиля. Новый профиль не сможет восстановить прежнюю переписку. Язык и компоновка панели сохраняются. Внешние экспорты и резервные копии остаются. Надёжное физическое стирание всех копий на устройстве не гарантируется.

В Linux Tokenlogue может сначала ограничить доступ к собственному поддерживаемому каталогу данных. Ошибка до начала удаления сохраняет профиль. Если права уже ограничены, каталог остаётся закрытым для других пользователей. Не удаляйте файлы и не меняйте права вручную для обхода ошибки.

Начатое удаление должно завершиться. При ошибке хранилища чаты остаются закрытыми. Нажмите `Завершить удаление` или перезапустите приложение, чтобы продолжить. Новая настройка откроется только после полного удаления. Для пустого профиля введите ключ и выберите новый PIN.

Локальное удаление не отзывает ключ OpenRouter, не удаляет аккаунт, не отменяет отправленные запросы и не возвращает списания. Если нужно сменить ключ с сохранением переписки, после входа используйте `Заменить ключ OpenRouter`.

[Руководство пользователя](user-guide.md#russian) · [Linux](linux-appimage.md#russian) · [Android](android.md#russian) · [Tokenlogue](../README.md#russian)
