# Tokenlogue AppImage

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This guide covers the Linux preview `0.1.0` built from application commit
`2b1f7d30e612416d8d88adde18a44aa235a7fe25`. Its interface is in Russian.
See the [user guide](user-guide.md#lang-en) for API-key setup and chat controls.

[Requirements](#en-requirements) | [Download](#en-download) |
[Run](#en-run) | [Troubleshooting](#en-help) | [Data and updates](#en-updates) |
[Recovery in current builds](#en-current-protection) |
[Delete local profile](#en-delete)

<a name="en-requirements"></a>

### Requirements

- Linux x86_64 with a graphical session and an x86-64-v2 compatible CPU.
  The included CPython 3.12.14 targets `x86_64_v2`. Ubuntu 22.04 is the system
  library baseline used for this build.
- System GTK3 and its dependencies, including GLib/GIO, Pango/Cairo,
  GdkPixbuf and accessibility libraries. GTK4 does not replace GTK3.
- Working graphics libraries and drivers supplied by your distribution.
- A user D-Bus session and a Secret Service provider such as GNOME Keyring.
  The bundled libsecret client cannot provide a key store by itself.
- FUSE for ordinary startup, or sufficient temporary disk space for
  [extract-and-run](#en-without-fuse).

You do not need to install Python, uv, Flutter SDK or compilation tools to
run this AppImage. An OpenRouter API key and network access are needed to
validate the key, obtain model information and exchange messages.
Wayland compatibility has not been verified.

<a name="en-download"></a>

### Download and verify

Open the [published preview 2b1f7d3](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3)
and download all six files into one folder:

- [Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage)
- [Tokenlogue-2b1f7d3-source-supplement.tar.gz](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz)
- [PROVENANCE.json](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/PROVENANCE.json)
- [RELEASE_NOTES.md](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/RELEASE_NOTES.md)
- [SOURCE_MATERIALS.md](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SOURCE_MATERIALS.md)
- [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SHA256SUMS)

No GitHub sign-in is needed. The AppImage does not need to be unpacked before
ordinary startup. Use this repository guide for launch instructions.
The [source-material guide](source-materials.md#lang-en) explains how to use
the supplement with the previous source bundle. This preview is unsigned.
Check the downloaded AppImage against the values below.

| Property | Value |
| --- | --- |
| File | `Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage` |
| Size in bytes | `32622984` |
| SHA-256 | `0852f9432cb089e31fef2722d84ce7124714588afb65d6f25cd64d0616a4779d` |

Open a terminal in the download folder containing all six files, then run
the command below.

```bash
sha256sum --check SHA256SUMS
```

The manifest lists the other five files, including the AppImage. All five
must report `OK`. It does not contain a checksum for itself.
The expected AppImage sum is also printed in the table. If it differs, download the
original file again. Do not replace the expected sum with the checksum
of the file that failed verification. A checksum detects changed bytes but
is not a publisher's signature.

<a name="en-run"></a>

### Ordinary startup

In the same download folder, grant execute permission.

```bash
chmod u+x ./Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage
```

Then start the application as your normal user.

```bash
./Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage
```

The Tokenlogue window will open. You can keep the AppImage in any convenient
folder. After granting execute permission, you can also open it through a
file manager that supports launching programs. The AppImage itself needs no
installation and does not automatically add an entry to the applications menu.

<a name="en-without-fuse"></a>

### Startup without FUSE

From the same folder, use the following option if FUSE is unavailable.

```bash
./Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage --appimage-extract-and-run
```

This option unpacks the AppImage into a temporary directory and starts
Tokenlogue without FUSE. Make sure the temporary directory has enough free
space for the unpacked files.

<a name="en-help"></a>

### Troubleshooting startup

| Symptom | What to check |
| --- | --- |
| Permission denied | Set execute permission and place the AppImage on a filesystem that allows execution. |
| FUSE mount error | Try the extract-and-run command above. |
| Missing GTK library | Install or repair GTK3 and its runtime dependencies through your distribution's package manager. |
| Key storage unavailable | Check that your user session has a running, unlocked Secret Service provider and D-Bus. |
| `Illegal instruction` | Check the processor's x86-64-v2 compatibility. A compatible Linux distribution alone is insufficient. |
| Graphics or loader error | Use a terminal to see the message and check your system graphics drivers and GTK3 installation. |

When reporting a startup problem through the
[project's issue tracker](https://github.com/Umichata/tokenlogue/issues), include
the AppImage filename, OS version, desktop/session type and the relevant error
text. Remove API keys and private conversation text before sharing it.

<a name="en-updates"></a>

### Data and updates

The database containing history and drafts is stored in the application data
directory, separately from the AppImage. Its content has no additional
encryption. The API key is kept separately in SecureStorage/Secret Service.
The [storage guide](user-guide.md#en-data) explains the role of the PIN and reset.

There is no automatic updater. Close Tokenlogue, verify the checksum of the
replacement file and start it under the same OS account. Replacing the AppImage
does not delete its data directory. Before switching back to an older version, make a backup of your application
data. Older versions may not support a database updated by a newer version.

<a name="en-current-protection"></a>

### Local protection and recovery in current Linux builds

This section applies to newer builds from the current source. It does not
describe the published `2b1f7d3` AppImage linked above. Current builds encrypt
conversation content and keep its separate key in Secret Service. Close all
older Tokenlogue copies before the first protected sign-in and keep them
closed while using the updated app. An older copy does not participate in
the new single-process protection.

Three incorrect app PIN checks lock PIN entry for five minutes, or 300 seconds.
Sign-in and confirmation before creating a recovery code share the limit.
Restart, language changes and sleep do not reset it. Recovery and local profile
deletion remain available. The [user guide](user-guide.md#en-current) explains
the countdown and updating an existing profile.

#### Save a recovery code before you need it

Current Linux builds offer a recovery code after successful PIN setup. For an
existing open profile, sign in, open `⋮` and choose `Recovery code`. Enter your
current app PIN again to issue a code or replace an existing one. An unlocked
keyring alone does not authorize issuing a code for a locked profile.

The code has 32 Base32 characters shown in groups of four. Save it separately
in a password manager or on paper, then enter that saved code to confirm.
Anyone who has the code can replace your app PIN. It is shown only on that
screen and cannot be revealed again after closing it. Copying requires your
explicit action. A clipboard manager may keep its own copy.

Until confirmation, a previous working code remains valid. Cancelling or a
failed save keeps that code and your working app PIN. After a confirmed
replacement, the previous code stops working. To see a new code later, sign
in and issue a replacement after entering your app PIN again.

#### Recover with a saved code

`Forgot PIN?` opens code entry without requiring system policy, administrator
rights or your Linux password. Enter the code previously saved for this
profile. ASCII letter case, ASCII spaces and hyphens are accepted. Keep all
32 characters. Tabs, line breaks, Unicode lookalikes and partial codes are
not accepted. Five incorrect code checks cause a separate 30-second lockout
that survives application restarts. The app PIN keeps its own limit.

After verification, choose and repeat a new app PIN and save it. Conversations
stay closed until saving finishes. Cancellation before the change is accepted
keeps your working PIN and code. Once the new PIN is saved, that recovery code
is consumed and cannot be used again. Save and confirm the new code offered
afterwards. If you close the app before completing that step, use your new PIN
to sign in and issue another code from `⋮`.

Recovery keeps your API key, original encryption key, history, drafts and
budgets. The code is an additional way to authorize a PIN change. It is not a
backup of the encryption key or database and cannot restore a key lost from
Secret Service. Keep the original secure storage available.

If this profile never had a recovery code, the screen explains that it cannot
create one while the profile is locked. A previously forgotten PIN is not
recovered retroactively by installing this update. You need the previous app
PIN, an already issued code or a working trusted system recovery method.
A new OpenRouter key, an unlocked keyring or a different Android profile does
not prove ownership of the locked Linux conversations. Your data stays in place.

Changing language, screen locking or sleep cancels an unfinished issuance or
recovery attempt and clears entered values. Opening `Forgot PIN?` does not
change the PIN. Your previous PIN stays valid until the new one is saved.
A new PIN already saved before locking remains active. Start a fresh recovery
attempt after returning if needed.

#### Optional system recovery

The separate `Use Linux system recovery` action starts the existing
polkit path only when you explicitly choose it. On Linux Mint 22.3 Cinnamon/X11
it requests fresh confirmation of your own Linux account through the desktop
agent. Type your Linux password only in that system window, never into
Tokenlogue. A different administrator account, an unlocked desktop or an
unlocked keyring does not replace this check. Every attempt requires a fresh
prompt. After success, choose, repeat and save a new app PIN. You can then
issue a recovery code.

This optional method needs the separately installed Tokenlogue policy and a
working desktop authentication agent. An unavailable trusted service, missing
policy, refusal or another failed check leaves conversations closed and shows
an explanation. A generic unavailable-service message alone does not establish
the underlying cause. Normal PIN sign-in and previously enrolled code recovery
remain separate methods. The AppImage does not install policy automatically.

#### Connect the optional policy separately

The AppImage cannot install system policy automatically. Review the
[policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) and
[installation helper](../packaging/linux/polkit/tokenlogue-polkit.py) from the
same source revision as your new build. The policy uses `auth_self` for the
active local account. It grants no root execution to Tokenlogue and keeps
no reusable authentication authorization.

Saved-code recovery needs none of the following system changes. If you choose
to enable only the optional system method, open a terminal at the root of that
checked repository and run this one-time administrative step.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
```

The helper verifies the policy checksum and installs only
`/usr/share/polkit-1/actions/io.github.umichata.tokenlogue.policy` with root
ownership and mode `0644`. It refuses an unexpected existing file. It does
not change PAM, Linux passwords or sign-in settings. Do not run the AppImage
with `sudo` or `pkexec`.

Check the installed policy as your ordinary user.

```bash
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

Restart Tokenlogue under your normal account and try this optional method
first with test data. The policy does not register a code for a locked profile
or unlock conversations by itself. To keep your conversations, use a valid
recovery method. The separate [profile-deletion action](#en-delete) gives up
that history and starts again. Do not export your encryption key or Linux
password into a file.

To remove only that verified policy later, use the separate administrative
removal step. Your application data remains in place.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a name="en-delete"></a>

#### Give up the old local profile and start again

To keep your conversations, use your app PIN or an existing recovery method.
The separate `Delete local profile` action at the bottom of `⋮` after sign-in
and on the PIN screen permanently gives up that profile inside the app.
It is available in current Linux and Android
builds even during a PIN lockout or when code and system recovery are unavailable.
It needs no old PIN, recovery code, administrator rights, system password or network.

Read the dialog, type the displayed phrase `DELETE PROFILE`, then choose
`Delete profile`. `Keep profile` cancels before confirmation.
Changing language, closing the dialog or a system lock also cancels a confirmation
that has not yet been accepted. Anyone who can use this screen can confirm
deletion. The phrase confirms intent and does not authenticate a person.

The menu action works even without a selected chat. Cancel before confirmation
to return to the same conversation and saved draft.

The PIN screen offers `Sign in`, `Delete local profile` and `Forgot PIN?`
in that order. Key replacement is available only in `⋮` after sign-in.
For a supported existing
Linux data folder, the same dialog also asks to make Tokenlogue's own folder
private before checking the profile again. No extra system permission or
manual chmod is needed. Cancelling before confirmation changes nothing.
Shared or unsupported folders are refused.

A failure before data deletion says that deletion has not started. Return to
the PIN screen and open a new confirmation as directed. If preparation already
made the folder private, it stays private and the profile is kept. This is
different from accepted deletion that still requires `Finish deletion`.

Deletion removes this profile's locally saved API key, PIN, recovery code,
encryption key, chats, messages, drafts, limits and local spending records.
It does not open the old conversations or carry them into the new registration.
Once data deletion has started, it must finish. If storage fails, access stays closed.
Use `Finish deletion` to retry without the forgotten PIN. Restarting
continues accepted deletion instead of opening a mixed old and new profile.
New setup appears only after the old profile's data and keys have been removed
and their absence checked.

Set up your API key and a new PIN again. The new profile has new protection
keys and an empty conversation list. A former PIN, code or saved recovery
attempt cannot open it. Interface language and panel layout are kept.
Other applications, external exports and backups remain untouched. This does
not promise physical erasure of SSD, swap or system snapshots.

Local API-key deletion does not revoke the key at OpenRouter, delete the
account or cancel requests already sent and their cost. `Replace OpenRouter
key` after sign-in remains a separate action that keeps conversations.
See the [complete deletion guide](user-guide.md#en-delete).

#### Screen lock and sleep

Current Linux builds monitor screen locking and sleep separately. On a supported
Cinnamon/X11 session, the normal system-lock handler closes access and keeps
the latest draft. Unlocking Linux does not sign you in. Enter the app PIN
again. Minimizing, losing focus and opening a system prompt are not proof of
screen locking. A request already sent may finish its accounting while access
stays closed.

Open the shield at the far right of the PIN screen's app header or beside
`⋮` in chat for the same `Local protection` panel. The panel is scrollable
and closes with its close button, Escape or an outside click. Closing it
returns focus to the shield and preserves PIN input and the chat draft.

You can inspect the public status before signing in. Choosing a test there
asks for your ordinary app PIN. Existing failures and lockout still apply.
After sign-in the same panel shows the selected test and `Start test`.
Only that explicit action requests OS locking or sleep. Normal sign-in does
not start a test. Cancel from the PIN form or close the reopened panel to
abandon the choice. Restart, recovery, profile deletion, a new system lock
and expiry cancel the choice too. In open chat the test buttons work directly.
Screen and sleep show separate results with the last completed check time.
Device history survives application restart, reboot and ordinary suspend.
Current monitoring is shown separately from the previous check.

Saving a new protected Linux profile and its PIN automatically opens
`Check local protection` before chats. Only `Start check` requests OS locking.
The saved profile remains usable, and no earlier manual OS lock is needed.
The check prepares a screen-locking service that has not started yet.
Bounded preparation shows its result and offers retry when unavailable.
Unlock the OS normally, then enter your saved app PIN. The result of the same
check remains visible after sign-in. Choose `Open chats` to finish the step.
If interrupted by restart, it resumes after normal PIN sign-in without
re-entering your API key. Replacing an existing key does not repeat setup.
`Continue with manual locking` opens chats while keeping protection unconfirmed.
The recovery-code offer follows completion of this step.

After sign-in, `Test screen lock` remains available from the details, including
an empty chat list and a new desktop session before its first screen lock. It saves your draft before
requesting a real OS lock. Screen confirmation does not confirm sleep.

`Test sleep protection` saves the draft and explicitly asks the OS to sleep.
Wake the computer, unlock Linux normally and enter your app PIN. The app
never sends the draft automatically. Sleep has its own result and does not
erase a successful screen check. A screen test is not required before sleep.
Opening details or saving registration does not start either OS action.
Ordinary sleep from the Linux menu also leaves screen history intact.

On reconnect, history stays visible with a separate current-monitoring warning.
After trusted compatible monitoring recovers, the previous confirmation
returns without a new manual test. An incompatible protection change can
require a new check. Denial, cancellation and an unproven attempt preserve
previous history. A proven failure is red for the affected mechanism.
Emergency closure cannot make it pass. A save error is shown explicitly.
Use manual app locking while a protection warning remains.

History belongs to this machine, application installation and OS account.
It lives outside the chat profile and is not included in conversation exports.
Copying preferences or chats to another machine does not copy green results.
Deleting a local profile does not delete device check history.

Use one active local Cinnamon/X11 desktop and one display. Additional displays,
other desktops and Wayland can limit screen monitoring. No system policy
installation, administrator rights or security-setting changes are needed.
Windows builds and its native desktop check are not currently provided.

#### Paid chat settings

In a paid chat, the strip above the conversation offers `Without confirmation`
before its first message. It starts off in new chats and keeps an existing
chat's saved choice after an update. Enabling it sends nothing by itself
and lets the first request, later requests and retries proceed without a
paid-request or price-change dialog. Current prices, required reserves and
limits still apply. Raising a spending limit still needs confirmation.
See [paid chat settings](user-guide.md#en-paid-confirmation) and
[chat metrics and estimates](user-guide.md#en-chat-metrics).

See the [current-build user guide](user-guide.md#en-current) for the shared
chat controls, language selection and recovery flow. The source-material
status remains `REVIEW_REQUIRED`. These Linux changes do not resolve the
separate Android 16KiB compatibility limitation.

### Related guides

The [source-material guide](source-materials.md#lang-en) describes the
available sources and the remaining gaps in the collection.
The [previous preview 986c6ad](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad)
remains available with the baseline source parts and runtime bundle.
If you have version `14b87ac`, see the [earlier preview guide](releases/v0.1.0-linux-preview.1.md#lang-en)
for its checksum and historical release details.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Руководство относится к предварительной Linux-сборке `0.1.0` из коммита
приложения `2b1f7d30e612416d8d88adde18a44aa235a7fe25`. Интерфейс на русском языке.
Настройка API-ключа и управление чатами описаны в
[руководстве пользователя](user-guide.md#lang-ru).

[Требования](#ru-requirements) | [Скачивание](#ru-download) |
[Запуск](#ru-run) | [Помощь при запуске](#ru-help) | [Данные и обновление](#ru-updates) |
[Восстановление в текущих сборках](#ru-current-protection) |
[Удаление локального профиля](#ru-delete)

<a name="ru-requirements"></a>

### Требования

- Linux x86_64 с графической сессией и процессором с поддержкой x86-64-v2.
  Встроенный CPython 3.12.14 собран для `x86_64_v2`. Базовая среда системных
  библиотек этой сборки - Ubuntu 22.04.
- Системная GTK3 и её зависимости, включая GLib/GIO, Pango/Cairo, GdkPixbuf
  и библиотеки доступности. GTK4 не заменяет GTK3.
- Работающие графические библиотеки и драйверы из вашего дистрибутива.
- Пользовательская D-Bus-сессия и поставщик Secret Service, например
  GNOME Keyring. Встроенный клиент libsecret сам по себе не создаёт хранилище.
- FUSE для обычного запуска или достаточно места во временном каталоге
  для [запуска с распаковкой](#ru-without-fuse).

Для запуска этого AppImage не нужно устанавливать Python, uv, Flutter SDK
или инструменты компиляции. API-ключ OpenRouter и доступ к сети нужны для
проверки ключа, получения сведений о моделях и обмена сообщениями.
Совместимость с Wayland не проверена.

<a name="ru-download"></a>

### Скачивание и проверка

Откройте [страницу опубликованной предварительной версии 2b1f7d3](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3)
и скачайте все шесть файлов в одну папку:

- [Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage)
- [Tokenlogue-2b1f7d3-source-supplement.tar.gz](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz)
- [PROVENANCE.json](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/PROVENANCE.json)
- [RELEASE_NOTES.md](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/RELEASE_NOTES.md)
- [SOURCE_MATERIALS.md](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SOURCE_MATERIALS.md)
- [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SHA256SUMS)

Вход в GitHub не нужен. Перед обычным запуском AppImage не требуется
распаковывать. Инструкция запуска находится в этом руководстве репозитория.
[Руководство по исходным материалам](source-materials.md#lang-ru) объясняет
использование дополнения вместе с прежним комплектом исходников.
Эта сборка не подписана. Сверьте скачанный AppImage со значениями ниже.

| Свойство | Значение |
| --- | --- |
| Файл | `Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage` |
| Размер в байтах | `32622984` |
| SHA-256 | `0852f9432cb089e31fef2722d84ce7124714588afb65d6f25cd64d0616a4779d` |

Откройте терминал в папке скачивания со всеми шестью файлами, затем выполните
следующую команду.

```bash
sha256sum --check SHA256SUMS
```

В файле сумм перечислены остальные пять файлов, включая AppImage. Все пять
должны получить результат `OK`. Сам файл сумм не содержит собственной суммы.
Ожидаемая сумма AppImage также указана в таблице. При несовпадении заново скачайте
исходный файл. Не заменяйте ожидаемую сумму хешем файла, который не прошёл
проверку. Контрольная сумма обнаруживает изменение байтов, но не является
подписью издателя.

<a name="ru-run"></a>

### Обычный запуск

В той же папке скачивания разрешите выполнение файла.

```bash
chmod u+x ./Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage
```

Затем запустите приложение от обычного пользователя.

```bash
./Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage
```

Откроется окно Tokenlogue. AppImage можно хранить в любой удобной папке.
После выдачи разрешения файл также можно открыть через файловый менеджер,
если он поддерживает запуск программ. Сам AppImage не требует установки
и не добавляет ярлык в меню приложений автоматически.

<a name="ru-without-fuse"></a>

### Запуск без FUSE

Если FUSE недоступен, выполните следующую команду в той же папке.

```bash
./Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage --appimage-extract-and-run
```

Эта команда распаковывает AppImage во временный каталог и запускает
Tokenlogue без FUSE. Убедитесь, что во временном каталоге достаточно свободного
места для распакованных файлов.

<a name="ru-help"></a>

### Помощь при запуске

| Симптом | Что проверить |
| --- | --- |
| Отказ в доступе | Выдайте разрешение на выполнение и поместите AppImage на файловую систему, где разрешён запуск программ. |
| Ошибка монтирования FUSE | Попробуйте указанную выше команду запуска с распаковкой. |
| Отсутствует библиотека GTK | Установите или восстановите GTK3 и её зависимости через менеджер пакетов дистрибутива. |
| Хранилище ключа недоступно | Проверьте работу D-Bus и запущенного, разблокированного Secret Service в своей пользовательской сессии. |
| `Illegal instruction` | Проверьте поддержку x86-64-v2 процессором. Одного подходящего дистрибутива Linux недостаточно. |
| Ошибка графики или загрузчика | Запустите из терминала, прочитайте сообщение и проверьте системные видеодрайверы и установку GTK3. |

При сообщении о проблеме запуска в
[разделе Issues проекта](https://github.com/Umichata/tokenlogue/issues) укажите
имя AppImage, версию ОС, окружение рабочего стола и тип сессии, а также текст
ошибки. Перед публикацией удалите API-ключи и личный текст переписки.

<a name="ru-updates"></a>

### Данные и обновление

База с историей и черновиками находится в каталоге данных приложения отдельно
от AppImage. Дополнительного шифрования содержимого нет. API-ключ хранится
отдельно в SecureStorage/Secret Service. Роль PIN и сброса описана в
[разделе о хранении](user-guide.md#ru-data).

Автоматического обновления нет. Закройте Tokenlogue, проверьте сумму нового
файла и запустите его под той же учётной записью ОС. Замена AppImage не удаляет
каталог данных. Перед возвратом к старой версии сохраните резервную копию данных приложения.
Старая версия может не поддерживать базу, обновлённую более новой версией.

<a name="ru-current-protection"></a>

### Локальная защита и восстановление в текущих сборках Linux

Этот раздел относится к новым сборкам из текущих исходников. Он не описывает
опубликованный AppImage `2b1f7d3`, на который даны ссылки выше. Текущие сборки
шифруют содержимое переписки и хранят отдельный ключ в Secret Service.
Перед первым входом с защитой переписки закройте все прежние копии Tokenlogue
и не запускайте их одновременно с обновлённым приложением. Прежняя копия
не участвует в новой защите от одновременной работы нескольких процессов.

Три неверные проверки PIN приложения блокируют ввод на пять минут, или
300 секунд. Вход и подтверждение перед созданием резервного кода используют
общее ограничение. Перезапуск, смена языка и сон его не сбрасывают.
Восстановление и удаление локального профиля остаются доступными.
[Руководство пользователя](user-guide.md#ru-current) описывает отсчёт
и обновление существующего профиля.

#### Сохраните резервный код заранее

Текущие сборки Linux предлагают резервный код после успешной настройки PIN.
Для существующего открытого профиля войдите, откройте `⋮` и выберите
`Резервный код`. Повторно введите действующий PIN приложения, чтобы выпустить
код или заменить прежний. Одной разблокированной связки ключей недостаточно
для выдачи кода закрытому профилю.

Код состоит из 32 символов Base32, показанных группами по четыре. Сохраните
его отдельно в менеджере паролей или на бумаге, затем подтвердите сохранение
повторным вводом. Обладающий кодом сможет заменить PIN приложения. Код
показывается только на этом экране. После его закрытия показать тот же код
заново нельзя. Копирование требует явного действия. Менеджер буфера обмена
может сохранить свою копию.

До подтверждения прежний действующий код сохраняется. Отмена или ошибка
сохранения оставляют этот код и действующий PIN приложения. После
подтверждённой замены прежний код перестаёт работать. Чтобы увидеть новый
код позже, войдите и выпустите замену после повторного ввода PIN приложения.

#### Восстановление по сохранённому коду

Кнопка `Забыли PIN?` открывает ввод кода без системной policy, прав
администратора и пароля Linux. Введите код, заранее сохранённый для этого
профиля. Регистр ASCII-букв, ASCII-пробелы и дефисы не имеют значения.
Сохраните все 32 символа. Табуляция, переносы строк, похожие Unicode-символы
и неполные коды не принимаются. Пять неверных проверок кода включают отдельную блокировку
на 30 секунд, которая сохраняется после перезапуска приложения. Для PIN
действует своё ограничение.

После проверки выберите и повторите новый PIN приложения, затем сохраните
его. Переписка остаётся закрытой до завершения сохранения. Отмена до принятия
изменения сохраняет действующий PIN и код. После сохранения нового PIN
использованный резервный код погашается и больше не действует. Сохраните
и подтвердите новый код, предложенный затем. Если закрыть приложение до
завершения этого шага, войдите с новым PIN и выпустите другой код через `⋮`.

Восстановление сохраняет API-ключ, прежний ключ шифрования, историю,
черновики и бюджеты. Код даёт дополнительное право сменить PIN. Он не является
резервной копией ключа шифрования или базы и не восстанавливает ключ,
потерянный из Secret Service. Сохраняйте исходное защищённое хранилище.

Если код для этого профиля никогда не выдавался, экран объяснит, что создать
его при закрытом профиле нельзя. Установка обновления не восстанавливает
ранее забытый PIN задним числом. Нужен прежний PIN приложения, уже выданный
код или работающий доверенный системный способ восстановления. Новый ключ
OpenRouter, разблокированная связка ключей и другой профиль Android не
подтверждают владение закрытой перепиской Linux. Данные остаются на месте.

Смена языка, системная блокировка или сон отменяют незавершённую выдачу
или восстановление и очищают введённые значения. Открытие `Забыли PIN?`
не меняет PIN. Прежний действует до сохранения нового. Если новый PIN уже
сохранился до блокировки, он остаётся действительным. При необходимости
после возврата начните новую попытку восстановления.

#### Дополнительное системное восстановление

Отдельное действие `Системное восстановление Linux`
запускает прежний путь polkit только по вашему явному выбору. В Linux Mint
22.3 Cinnamon/X11 он запрашивает новое подтверждение собственной учётной
записи Linux через агент рабочего стола. Вводите пароль Linux только
в системном окне, а не в Tokenlogue. Другая учётная запись администратора,
открытый рабочий стол и разблокированная связка ключей не заменяют эту
проверку. Каждая попытка требует нового запроса. После успеха выберите,
повторите и сохраните новый PIN приложения. Затем можно выдать резервный код.

Дополнительному способу нужны отдельно установленная policy Tokenlogue
и работающий агент системного подтверждения. Недоступная доверенная служба,
отсутствующая policy, отказ или другая неудачная проверка оставляют переписку
закрытой с объяснением. Одно обобщённое сообщение о недоступной службе не
доказывает причину сбоя. Обычный вход по PIN и заранее выданному коду остаются
отдельными способами. AppImage не устанавливает policy автоматически.

#### Отдельное подключение дополнительной policy

AppImage не устанавливает системную policy автоматически. Проверьте
[policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy)
и [установщик](../packaging/linux/polkit/tokenlogue-polkit.py) из той же
ревизии исходников, что и новая сборка. Policy использует `auth_self`
для активной локальной учётной записи. Она не даёт Tokenlogue запускаться
с правами root и не сохраняет повторно используемое системное разрешение.

Восстановление по сохранённому коду не требует перечисленных ниже системных
изменений. Если вы решили подключить только дополнительный системный способ,
откройте терминал в корне этого проверенного репозитория и выполните разовый
административный шаг.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
```

Установщик проверяет контрольную сумму policy и устанавливает только
`/usr/share/polkit-1/actions/io.github.umichata.tokenlogue.policy`
с владельцем root и правами `0644`. Неожиданный существующий файл он
не перезаписывает. PAM, пароли Linux и настройки входа не меняются.
Не запускайте AppImage через `sudo` или `pkexec`.

Проверьте установленную policy от обычного пользователя.

```bash
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

Перезапустите Tokenlogue под своей обычной учётной записью и сначала
проверьте этот дополнительный способ на тестовых данных. Сама policy не
выдаёт код закрытому профилю и не открывает переписку. Чтобы сохранить
переписку, используйте действующий способ восстановления. Отдельное
[удаление профиля](#ru-delete) означает отказ от этой истории и начало заново.
Не экспортируйте ключ шифрования или пароль Linux в открытый файл.

Для последующего удаления только этой проверенной policy выполните отдельный
административный шаг. Данные приложения останутся на месте.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a name="ru-delete"></a>

#### Отказ от прежнего локального профиля и начало заново

Чтобы сохранить переписку, используйте PIN приложения или уже действующий
способ восстановления. Отдельное действие `Удалить локальный профиль`
внизу `⋮` после входа и на экране PIN окончательно убирает этот профиль
из приложения. Оно доступно
в текущих сборках Linux и Android даже при временной блокировке ввода PIN
и недоступности восстановления по коду или через систему. Прежний PIN,
резервный код, права администратора, системный пароль и сеть не нужны.

Прочитайте диалог, введите показанную фразу `УДАЛИТЬ ПРОФИЛЬ`, затем нажмите
`Удалить профиль`. Кнопка `Сохранить профиль` отменяет действие
до подтверждения. Смена языка, закрытие диалога или системная блокировка также
отменяют ещё не принятое подтверждение. Подтвердить удаление может любой
с доступом к этому экрану. Фраза подтверждает намерение, а не личность.

Действие в меню доступно и без выбранного чата. Отмена до подтверждения
возвращает ту же переписку и сохранённый черновик.

На экране PIN действия идут в порядке `Войти`, `Удалить локальный профиль`,
`Забыли PIN?`. Замена ключа доступна только в `⋮` после входа.
Для поддерживаемого
существующего каталога Linux тот же диалог также просит разрешить ограничение
доступа к собственному каталогу Tokenlogue перед повторной проверкой профиля.
Дополнительные системные права и ручной chmod не нужны. Отмена до подтверждения
ничего не меняет. Общие и неподдерживаемые каталоги отклоняются.

Отказ до удаления данных сообщает, что удаление не началось. Вернитесь к экрану
PIN и откройте новое подтверждение согласно сообщению. Если подготовка уже
ограничила доступ к каталогу, он останется таким, а профиль сохранится.
Это отличается от принятого удаления, для которого нужно действие
`Завершить удаление`.

Удаляются локальные API-ключ, PIN, резервный код, ключ шифрования, чаты,
сообщения, черновики, лимиты и локальный учёт расходов этого профиля.
Прежняя переписка не открывается и не переносится в новую регистрацию.
После начала удаления данных его нужно завершить. При ошибке
хранилища доступ остаётся закрытым. Нажмите `Завершить удаление`,
чтобы повторить без забытого PIN. Перезапуск продолжает принятое удаление,
а не открывает смешанный старый и новый профиль. Новая настройка появится
только после удаления прежних данных и ключей и проверки их отсутствия.

Заново настройте API-ключ и новый PIN. У нового профиля новые ключи защиты
и пустой список переписки. Прежние PIN, код и сохранённая попытка
восстановления его не открывают. Язык интерфейса и расположение панели
сохраняются. Другие приложения, внешние экспорты и резервные копии не
затрагиваются. Физическое стирание SSD, swap и снимков системы не гарантируется.

Локальное удаление API-ключа не отзывает его в OpenRouter, не удаляет аккаунт
и не отменяет уже отправленные запросы и их стоимость. `Заменить ключ
OpenRouter` после входа остаётся отдельным действием с сохранением переписки.
Подробнее в [полном руководстве по удалению](user-guide.md#ru-delete).

#### Блокировка экрана и сон

Текущие сборки Linux наблюдают экранную блокировку и сон отдельно.
В поддерживаемой сессии Cinnamon/X11 штатная системная блокировка закрывает
доступ с сохранением последнего черновика. Разблокировка Linux не выполняет
вход в приложение. Снова введите его PIN. Сворачивание, потеря фокуса и показ
системного запроса не доказывают блокировку экрана. Уже отправленный запрос
может завершить учёт расходов при закрытом доступе.

Щит крайним справа в шапке экрана PIN или рядом с `⋮` в чате открывает
одну и ту же панель `Локальная защита`. Она прокручивается и закрывается
кнопкой закрытия, Escape или нажатием снаружи. Закрытие возвращает фокус
к щиту и сохраняет ввод PIN и черновик чата.

Несекретный статус доступен до входа. Выбор теста на этом экране предлагает
обычный вход по PIN приложения. Прежние ошибки и ограничение попыток
сохраняются. После входа та же панель показывает выбранный тест
и `Начать тест`. Только это явное действие запрашивает блокировку ОС
или сон. Обычный вход не запускает проверку. Для отмены используйте
кнопку в форме PIN или закройте вновь открытую панель. Перезапуск,
восстановление, удаление профиля, новая системная блокировка и истечение
срока также отменяют выбор. В открытом чате кнопки работают напрямую.
Экран и сон показывают отдельные результаты со временем последней
завершённой проверки. История устройства переживает перезапуск приложения,
перезагрузку и обычный suspend. Текущее наблюдение показывается отдельно
от прежней проверки.

После сохранения нового защищённого профиля Linux и его PIN автоматически
открывается `Проверка локальной защиты` до перехода к чатам. Блокировка ОС
запрашивается только кнопкой `Начать проверку`. Сохранённый профиль остаётся
доступным, предварительная ручная блокировка ОС не нужна. Проверка готовит
ещё не запущенную экранную службу. Подготовка ограничена по времени
и показывает результат с повтором при недоступности. Разблокируйте ОС
обычным способом, затем введите сохранённый PIN приложения. Результат того же
теста остаётся видимым после входа. Нажмите `Перейти к чатам`, чтобы завершить
шаг. После перезапуска он возобновляется при обычном входе по PIN без
повторного ввода API-ключа. Замена существующего ключа не повторяет настройку.
`Продолжить с ручной блокировкой` открывает чаты с неподтверждённой защитой.
После завершения этого шага предлагается резервный код.

После входа `Тест блокировки` остаётся доступен в подробностях, в том числе
при пустом списке чатов и в новой сессии рабочего стола до первой блокировки экрана. Он сохраняет
черновик перед запросом настоящей блокировки ОС. Подтверждение экрана
не подтверждает сон.

`Тест перехода в сон` сохраняет черновик и явно запрашивает сон ОС.
Пробудите компьютер, разблокируйте Linux обычным способом и введите PIN
приложения. Черновик автоматически не отправляется. У сна свой результат,
который не стирает успешную экранную проверку. Экранный тест перед сном
не требуется. Открытие подробностей и сохранение регистрации не запускают
эти действия ОС. Обычный сон из меню Linux также сохраняет историю экрана.

При переподключении история видна с отдельным предупреждением о текущем
наблюдении. После восстановления доверенного совместимого наблюдения
прежнее подтверждение возвращается без нового ручного теста. Несовместимое
изменение защиты может потребовать повторной проверки. Отказ запроса,
отмена и недоказанная попытка сохраняют прежнюю историю. Доказанный отказ
красный только у соответствующего механизма. Аварийное закрытие не делает
его успешным. Ошибка записи показывается явно. Пока предупреждение
о защите остаётся, блокируйте приложение вручную.

История относится к этой машине, установке приложения и учётной записи ОС.
Она хранится вне профиля чатов и не входит в экспорт переписки. Копирование
предпочтений или чатов на другую машину не переносит зелёные результаты.
Удаление локального профиля не удаляет историю проверки устройства.

Используйте один активный локальный рабочий стол Cinnamon/X11 и один экран.
Дополнительные экраны, другие рабочие столы и Wayland могут ограничивать
наблюдение. Установка policy, права администратора и изменение настроек
безопасности не нужны. Сборки Windows и нативная проверка её рабочего стола
сейчас не предоставляются.

#### Настройки платного чата

В платном чате полоса над перепиской предлагает `Без подтверждений`
до первого сообщения. В новых чатах настройка изначально выключена,
а прежние сохраняют свой выбор после обновления. Само включение ничего
не отправляет и позволяет первому, следующим запросам и повторам проходить
без диалога платного запроса или изменения цены. Текущие цены, необходимые
резервы и лимиты сохраняются. Увеличение денежного лимита по-прежнему требует
подтверждения. Подробнее в [настройках платного чата](user-guide.md#ru-paid-confirmation)
и [статистике и оценке](user-guide.md#ru-chat-metrics).

Общие элементы чата, выбор языка и восстановление описаны в
[руководстве текущих сборок](user-guide.md#ru-current). Статус исходных
материалов остаётся `REVIEW_REQUIRED`. Эти изменения Linux не устраняют
отдельное ограничение совместимости Android с размером страниц 16KiB.

### Другие руководства

[Руководство по исходным материалам](source-materials.md#lang-ru) описывает
доступные исходники и недостающие части комплекта.
[Прежняя предварительная версия 986c6ad](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad)
сохранена вместе с базовыми частями исходного архива и комплектом runtime.
Для версии `14b87ac` используйте [описание прежней сборки](releases/v0.1.0-linux-preview.1.md#lang-ru).
В нём приведены её контрольная сумма и сведения о прежней сборке.

[К Tokenlogue](../README.md#lang-ru)
