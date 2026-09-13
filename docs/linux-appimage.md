# Tokenlogue AppImage

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This guide covers the Linux preview `0.1.0` built from application commit
`1472c00d38a87dddfa33cdb8c9c0d3b6aadb02f6`. Its interface is in Russian.
See the [user guide](user-guide.md#lang-en) for API-key setup and chat controls.

[Requirements](#en-requirements) | [Download](#en-download) |
[Run](#en-run) | [Troubleshooting](#en-help) | [Data and updates](#en-updates)

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

Open the [preview artifact page on GitHub Actions](https://github.com/Umichata/tokenlogue/actions/runs/34759960235)
and select `verified-appimage-34759960235` under **Artifacts**. Sign in to
GitHub if required. Extract the downloaded ZIP. It contains the AppImage,
`SHA256SUMS` and `provenance.json`.

GitHub Actions keeps artifacts for a limited time and may require access
through your account. The download link will stop working when the artifact
expires. This preview is unsigned. Check the downloaded file against the
values below.

| Property | Value |
| --- | --- |
| File | `Tokenlogue-0.1.0-1472c00-x86_64.AppImage` |
| Size in bytes | `32618888` |
| SHA-256 | `377554046e9e177ce0abb4d9ab0605d033098ebbe81ef6542b6261a796f7b6b4` |

Open a terminal in the extracted folder containing the AppImage and
`SHA256SUMS`, then run the command below.

```bash
sha256sum --check SHA256SUMS
```

Continue only if the command reports `OK` for the exact filename above.
The expected sum is also printed in the table. If it differs, download the
original artifact again. Do not replace the expected sum with the checksum
of the file that failed verification. A checksum detects changed bytes but
is not a publisher's signature.

<a name="en-run"></a>

### Ordinary startup

In the same extracted folder, grant execute permission.

```bash
chmod u+x ./Tokenlogue-0.1.0-1472c00-x86_64.AppImage
```

Then start the application as your normal user.

```bash
./Tokenlogue-0.1.0-1472c00-x86_64.AppImage
```

The Tokenlogue window will open. You can keep the AppImage in any convenient
folder. After granting execute permission, you can also open it through a
file manager that supports launching programs. The AppImage itself needs no
installation and does not automatically add an entry to the applications menu.

<a name="en-without-fuse"></a>

### Startup without FUSE

From the same folder, use the following option if FUSE is unavailable.

```bash
./Tokenlogue-0.1.0-1472c00-x86_64.AppImage --appimage-extract-and-run
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

### Related guides

The [source-material guide](source-materials.md#lang-en) describes the
available sources and the remaining gaps in the collection.
If you have version `14b87ac`, see the [earlier preview guide](releases/v0.1.0-linux-preview.1.md#lang-en)
for its checksum and differences from this version.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Руководство относится к предварительной Linux-сборке `0.1.0` из коммита
приложения `1472c00d38a87dddfa33cdb8c9c0d3b6aadb02f6`. Интерфейс на русском языке.
Настройка API-ключа и управление чатами описаны в
[руководстве пользователя](user-guide.md#lang-ru).

[Требования](#ru-requirements) | [Скачивание](#ru-download) |
[Запуск](#ru-run) | [Помощь при запуске](#ru-help) | [Данные и обновление](#ru-updates)

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

Откройте [страницу артефакта в GitHub Actions](https://github.com/Umichata/tokenlogue/actions/runs/34759960235)
и выберите `verified-appimage-34759960235` в разделе **Artifacts**. При
необходимости войдите в GitHub. Распакуйте скачанный ZIP. В нём находятся
AppImage, `SHA256SUMS` и `provenance.json`.

GitHub Actions хранит артефакты ограниченное время и может запрашивать
доступ через вашу учётную запись. После истечения срока хранения ссылка
перестанет работать. Эта сборка не подписана. Сверьте скачанный файл
со значениями ниже.

| Свойство | Значение |
| --- | --- |
| Файл | `Tokenlogue-0.1.0-1472c00-x86_64.AppImage` |
| Размер в байтах | `32618888` |
| SHA-256 | `377554046e9e177ce0abb4d9ab0605d033098ebbe81ef6542b6261a796f7b6b4` |

Откройте терминал в распакованной папке с AppImage и `SHA256SUMS`, затем
выполните следующую команду.

```bash
sha256sum --check SHA256SUMS
```

Продолжайте только после результата `OK` для точного имени файла из таблицы.
Ожидаемая сумма также указана в таблице. При несовпадении заново скачайте
исходный артефакт. Не заменяйте ожидаемую сумму хешем файла, который не прошёл
проверку. Контрольная сумма обнаруживает изменение байтов, но не является
подписью издателя.

<a name="ru-run"></a>

### Обычный запуск

В той же распакованной папке разрешите выполнение файла.

```bash
chmod u+x ./Tokenlogue-0.1.0-1472c00-x86_64.AppImage
```

Затем запустите приложение от обычного пользователя.

```bash
./Tokenlogue-0.1.0-1472c00-x86_64.AppImage
```

Откроется окно Tokenlogue. AppImage можно хранить в любой удобной папке.
После выдачи разрешения файл также можно открыть через файловый менеджер,
если он поддерживает запуск программ. Сам AppImage не требует установки
и не добавляет ярлык в меню приложений автоматически.

<a name="ru-without-fuse"></a>

### Запуск без FUSE

Если FUSE недоступен, выполните следующую команду в той же папке.

```bash
./Tokenlogue-0.1.0-1472c00-x86_64.AppImage --appimage-extract-and-run
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

### Другие руководства

[Руководство по исходным материалам](source-materials.md#lang-ru) описывает
доступные исходники и недостающие части комплекта.
Для версии `14b87ac` используйте [описание прежней сборки](releases/v0.1.0-linux-preview.1.md#lang-ru).
В нём приведены её контрольная сумма и отличия от этой версии.

[К Tokenlogue](../README.md#lang-ru)
