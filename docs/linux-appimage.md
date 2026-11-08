# Tokenlogue for Linux / Tokenlogue для Linux

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

Run Tokenlogue as an AppImage on a Linux desktop. Python, Flutter and build tools are included or unnecessary for normal use. The current preview has an English and Russian interface.

[Requirements](#en-requirements) · [Download](#en-download) · [Run](#en-run) · [Update](#en-updates) · [Troubleshooting](#en-help)

<a id="en-requirements"></a>

### Requirements

- Linux x86_64 and an x86-64-v2 compatible processor. The system-library baseline is Ubuntu 22.04.
- A graphical desktop, GTK3 and its runtime dependencies. GTK4 alone does not replace GTK3.
- Working graphics drivers supplied by your distribution.
- A user D-Bus session and an available, unlocked Secret Service provider such as GNOME Keyring. The bundled libsecret client is not a key store by itself.
- FUSE for ordinary startup, or temporary disk space for extract-and-run.
- An OpenRouter API key and internet access to validate the key, load models and send messages.

Screen-lock and sleep protection is designed for the supported Cinnamon/X11 desktop session. Other desktops and Wayland can have limited automatic monitoring. Check the app's protection panel and use manual app locking when needed.

<a id="en-download"></a>

### Download and verify

The [Releases page](https://github.com/Umichata/tokenlogue/releases) lists publicly available packages. The current Linux and Android preview has not yet been published there. Its Linux package is identified below for users who received the preview bundle.

| Current preview file | Value |
| --- | --- |
| AppImage | `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` |
| Size | 35,350,920 bytes |
| SHA-256 | `227ad9991dc0b00dfd160003967de6b9a321078b89f6129d0fdd2a620cf8c1ae` |

Download the checksum file supplied with the same package. Open a terminal in that folder and verify it.

```bash
sha256sum --check SHA256SUMS
```

Every listed file must report `OK`. A checksum detects changed bytes but does not replace a publisher's signature. This AppImage is unsigned. Do not replace an expected checksum with the hash of a file that failed verification.

The [earlier published Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) remains a separate version. It uses `Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage`, with SHA-256 `0852f9432cb089e31fef2722d84ce7124714588afb65d6f25cd64d0616a4779d`. Its Russian-only interface and older data-protection behavior differ from this guide. Use its own checksum file and [release notes](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/RELEASE_NOTES.md) when identifying older packages.

<a id="en-run"></a>

### Start Tokenlogue

Grant execute permission once, then start the verified AppImage as your normal user.

```bash
chmod u+x ./Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage
./Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage
```

You can keep the file in a convenient folder. A file manager that supports program launching can open it after execute permission is set. The AppImage does not automatically add a menu entry. Do not run it with `sudo` or `pkexec`.

<a id="en-without-fuse"></a>

### Run without FUSE

If your system cannot mount AppImages through FUSE, use extract-and-run.

```bash
./Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage --appimage-extract-and-run
```

This unpacks files to a temporary directory and starts the app without FUSE. Ensure that the temporary filesystem has enough space for the extracted files.

<a id="en-updates"></a>

### Update without removing your profile

Close every older Tokenlogue copy before opening the replacement. Verify the new file and run it under the same OS account. There is no automatic updater. Replacing the AppImage does not remove the separately stored application data.

At the first successful sign-in, older unprotected conversation content is converted before chats open. Keep older copies closed throughout. Do not downgrade a profile without a compatible backup. Earlier versions may not understand the updated database or its protection.

The database alone is not a complete portable backup. Its encryption key stays in the system key store. Losing that key can make history unrecoverable. Read [conversation protection](security.md#en-encryption) before moving data or changing keyring settings.

<a id="en-current-protection"></a>
<a id="en-system-recovery"></a>

### Optional recovery through your Linux account

A saved [recovery code](security.md#en-recovery) is the usual Linux PIN-recovery method. It needs no administrator setup. The optional `Use Linux system recovery` action requires a Tokenlogue polkit policy and the desktop authentication agent.

If you choose this optional method, review the [policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) and [installation helper](../packaging/linux/polkit/tokenlogue-polkit.py) from the source package matching your app. From the repository root, the one-time installation command is below. This installs the policy, not the application.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
```

Check the installed policy as your ordinary user.

```bash
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

The helper installs only the verified Tokenlogue policy. It refuses unexpected existing files and does not change Linux passwords, PAM or login settings. Tokenlogue is still run as your ordinary user. Each recovery attempt requires fresh confirmation of your own account in the system window. Enter the Linux password only there.

To remove only that policy later, use the following command. Application data stays in place.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a id="en-help"></a>

### Troubleshoot startup

| Problem | What to check |
| --- | --- |
| Permission denied | Execute permission and a filesystem that permits launching programs. |
| FUSE mount error | Try extract-and-run above. |
| Missing GTK library | Repair GTK3 and its runtime dependencies through your distribution's package manager. |
| Key storage unavailable | Unlock the Secret Service provider and check your user D-Bus session. Keep the existing profile files. |
| Illegal instruction | Confirm that the CPU supports x86-64-v2. |
| Graphics error | Check system graphics drivers and GTK3. Terminal output may explain the failure. |
| Another copy is running | Close the other copy using the same data folder. Do not bypass the profile lock. |

For [a support request](https://github.com/Umichata/tokenlogue/issues), include the package filename, distribution, desktop session and relevant error. Remove API keys, private messages and personal paths before sharing.

<a id="en-delete"></a>

[First connection and chat controls](user-guide.md#english) · [PIN, recovery and profile deletion](security.md#english) · [Sources and licenses](source-materials.md#english) · [Tokenlogue](../README.md#english)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Запускайте Tokenlogue на рабочем столе Linux в формате AppImage. Для обычного использования не нужно отдельно устанавливать Python, Flutter или инструменты сборки. В текущей предварительной версии есть русский и английский интерфейс.

[Требования](#ru-requirements) · [Скачивание](#ru-download) · [Запуск](#ru-run) · [Обновление](#ru-updates) · [Помощь](#ru-help)

<a id="ru-requirements"></a>

### Требования

- Linux x86_64 и процессор с поддержкой x86-64-v2. Базовая среда системных библиотек — Ubuntu 22.04.
- Графический рабочий стол, GTK3 и его зависимости. Одного GTK4 недостаточно.
- Работающие графические драйверы вашего дистрибутива.
- Пользовательская сессия D-Bus и доступный разблокированный Secret Service, например GNOME Keyring. Включённый клиент libsecret сам по себе не является хранилищем ключей.
- FUSE для обычного запуска или место во временном каталоге для extract-and-run.
- API-ключ OpenRouter и интернет для проверки ключа, загрузки моделей и отправки сообщений.

Защита при блокировке экрана и сне рассчитана на поддерживаемую сессию Cinnamon/X11. В других окружениях и Wayland автоматическое наблюдение может быть ограничено. Проверяйте панель защиты приложения и при необходимости блокируйте его вручную.

<a id="ru-download"></a>

### Скачивание и проверка

На странице [Releases](https://github.com/Umichata/tokenlogue/releases) находятся общедоступные пакеты. Текущая предварительная версия Linux и Android там пока не опубликована. Ниже указан её Linux-пакет для пользователей, получивших комплект предварительной версии.

| Файл текущей версии | Значение |
| --- | --- |
| AppImage | `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` |
| Размер | 35 350 920 байт |
| SHA-256 | `227ad9991dc0b00dfd160003967de6b9a321078b89f6129d0fdd2a620cf8c1ae` |

Получите файл сумм из того же комплекта. Откройте терминал в этой папке и выполните проверку.

```bash
sha256sum --check SHA256SUMS
```

Для каждого перечисленного файла должно появиться `OK`. Сумма обнаруживает изменение байтов, но не заменяет подпись издателя. Эта AppImage не подписана. Не подменяйте ожидаемую сумму хешем файла, который не прошёл проверку.

[Прежний опубликованный Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) остаётся отдельной версией. Его файл называется `Tokenlogue-0.1.0-2b1f7d3-x86_64.AppImage`, а SHA-256 равен `0852f9432cb089e31fef2722d84ce7124714588afb65d6f25cd64d0616a4779d`. Русский интерфейс и прежняя защита данных отличаются от описанных здесь. Для проверки старых пакетов используйте их файл сумм и [примечания к выпуску](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/RELEASE_NOTES.md).

<a id="ru-run"></a>

### Запуск Tokenlogue

Один раз разрешите исполнение и запустите проверенную AppImage от своего обычного пользователя.

```bash
chmod u+x ./Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage
./Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage
```

Хранить файл можно в удобной папке. После выдачи прав его можно открыть через файловый менеджер, поддерживающий запуск программ. AppImage не добавляет пункт меню автоматически. Не запускайте её через `sudo` или `pkexec`.

<a id="ru-without-fuse"></a>

### Запуск без FUSE

Если система не может монтировать AppImage через FUSE, используйте extract-and-run.

```bash
./Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage --appimage-extract-and-run
```

Программа распакует файлы во временный каталог и запустится без FUSE. Убедитесь, что во временной файловой системе хватает места для распакованных файлов.

<a id="ru-updates"></a>

### Обновление с сохранением профиля

Перед запуском замены закройте все прежние копии Tokenlogue. Проверьте новый файл и запустите его в той же учётной записи ОС. Автоматического обновления нет. Замена AppImage не удаляет отдельно сохранённые данные приложения.

При первом успешном входе ранее незащищённая переписка преобразуется до открытия чатов. Всё это время держите прежние копии закрытыми. Не возвращайтесь к старой версии профиля без совместимой резервной копии. Прежние версии могут не понимать обновлённую базу и её защиту.

Одна база не является полной переносимой резервной копией. Ключ шифрования остаётся в системном хранилище. Его потеря может сделать переписку невосстановимой. Перед переносом данных или изменением связки ключей прочитайте [о защите переписки](security.md#ru-encryption).

<a id="ru-current-protection"></a>
<a id="ru-system-recovery"></a>

### Необязательное восстановление через учётную запись Linux

Основной способ восстановления PIN в Linux — заранее сохранённый [резервный код](security.md#ru-recovery). Для него не нужна настройка администратора. Дополнительный пункт `Системное восстановление Linux` требует policy Tokenlogue для polkit и системного агента аутентификации.

Если вы выбираете этот способ, изучите [policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) и [помощник установки](../packaging/linux/polkit/tokenlogue-polkit.py) из исходного комплекта, соответствующего приложению. Однократная команда установки приведена ниже. Выполняйте её из корня репозитория. Она устанавливает policy, а не приложение.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
```

Проверьте установленную policy от обычного пользователя.

```bash
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

Помощник устанавливает только проверенную policy Tokenlogue. Он отказывается заменять неожиданные файлы и не меняет пароли Linux, PAM или настройки входа. Сам Tokenlogue по-прежнему запускается обычным пользователем. Каждая попытка восстановления требует нового подтверждения вашей учётной записи в системном окне. Вводите пароль Linux только там.

Для удаления только этой policy используйте команду ниже. Данные приложения сохранятся.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a id="ru-help"></a>

### Помощь при запуске

| Проблема | Что проверить |
| --- | --- |
| Отказано в доступе | Право исполнения и возможность запуска программ на выбранной файловой системе. |
| Ошибка монтирования FUSE | Попробуйте extract-and-run выше. |
| Не найдена библиотека GTK | Восстановите GTK3 и его зависимости через пакетный менеджер дистрибутива. |
| Хранилище ключей недоступно | Разблокируйте Secret Service и проверьте пользовательскую сессию D-Bus. Сохраните файлы профиля. |
| Illegal instruction | Убедитесь, что процессор поддерживает x86-64-v2. |
| Ошибка графики | Проверьте драйверы системы и GTK3. Сообщение в терминале может объяснить причину. |
| Уже работает другая копия | Закройте другую копию с тем же каталогом данных. Не обходите блокировку профиля. |

В [обращении за помощью](https://github.com/Umichata/tokenlogue/issues) укажите имя пакета, дистрибутив, рабочее окружение и существенную ошибку. Перед отправкой уберите API-ключи, личную переписку и персональные пути.

<a id="ru-delete"></a>

[Подключение и работа с чатами](user-guide.md#russian) · [PIN, восстановление и удаление профиля](security.md#russian) · [Исходники и лицензии](source-materials.md#russian) · [Tokenlogue](../README.md#russian)
