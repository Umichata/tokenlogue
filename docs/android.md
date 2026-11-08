# Tokenlogue for Android / Tokenlogue для Android

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

Tokenlogue brings OpenRouter chats to an ARM64 Android phone or tablet. The interface supports English and Russian, saved per-chat drafts and layouts that adapt to the available space.

[Requirements](#en-requirements) · [Install](#en-install) · [Update](#en-update) · [First launch](#en-first-launch) · [Protection](security.md#english)

<a id="en-requirements"></a>

### Requirements and compatibility

- Android 7.0 or later, API 24 or newer.
- An ARM64 device that supports the `arm64-v8a` ABI.
- An OpenRouter API key and internet access for key validation, models and messages.
- A supported device screen lock for optional system PIN recovery on Android 11 or later.

The minimum API level does not mean that every Android version or device has been tested. The current package passed static ELF and ZIP alignment checks for 4 KiB and 16 KiB pages. Running it on a native ARM64 device with a 16 KiB kernel has not been checked. An earlier package's launch through ARM translation is not such a check for this package.

<a id="en-install"></a>

### Obtain and install the APK

There is currently no publicly downloadable Android APK on the project's [Releases page](https://github.com/Umichata/tokenlogue/releases). Use the APK provided with the current preview bundle. The existing published Linux release is a different package.

| Current Android preview | Value |
| --- | --- |
| APK | `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk` |
| Version | `0.1.0`, versionCode `41` |
| Size | 56,160,490 bytes |
| SHA-256 | `2f7c699960e3967220f526245ca2acbf4335104a141ccf3fa2b8a04dae4709d9` |
| Signing certificate SHA-256 | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

Verify the APK against the bundle's `SHA256SUMS` before installation. On Linux, run the following command from the folder containing those files.

```bash
sha256sum --check SHA256SUMS
```

All listed files must report `OK`. Transfer the verified APK to the device, open it and follow Android's installer. Android may ask to allow installations from the file manager or browser you used. Grant that permission only if you trust the package. You can turn it off again afterwards.

<a id="en-update"></a>

### Update a compatible installation

Install the new APK over the compatible existing installation with the same application identity and signing certificate. Keep the existing application data. Uninstalling or clearing data is not an ordinary update step and can make encrypted conversations unrecoverable.

If Android refuses the update, check the package version, architecture and signing identity. Do not remove the old app just to bypass a signature error. Keep the existing data and ask for help.

<a id="en-first-launch"></a>

### Connect and start chatting

<img src="assets/screenshots/android-start.png" alt="First launch of Android" width="320">

First launch of Android.

Choose a language, enter your OpenRouter API key and select `Check key`. Choose and repeat a four-digit app PIN, then save it. Use `+` to choose free or paid mode, a model and limits. The [user guide](user-guide.md#english) explains chats, drafts and cost information.

The top-left button opens the chat drawer. Select a chat, tap outside or press Back to close it. The keyboard can reduce the space for header actions. Dismiss it to show the rename and delete shortcuts again.

### Protect the local profile

Moving Tokenlogue to the background closes access. Enter the app PIN when returning. Your saved draft is restored. Unlocking Android does not unlock Tokenlogue automatically.

On supported Android 11 or later devices, `Forgot PIN?` requests fresh system verification before letting you save a new app PIN. The old PIN and conversations remain if you cancel. See [recovery and encryption](security.md#en-recovery).

Android application backup is disabled. The app uses internet access and system authentication capabilities. It does not request microphone access. Changing device security, uninstalling or clearing data can affect the keys needed to read protected conversations. A copied database alone is not a portable backup.

[User guide](user-guide.md#english) · [Protection](security.md#english) · [Source materials](source-materials.md#english) · [Tokenlogue](../README.md#english)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Tokenlogue позволяет общаться с моделями OpenRouter на телефоне или планшете Android ARM64. Есть русский и английский интерфейс, отдельные черновики чатов и компоновка, которая учитывает доступное место.

[Требования](#ru-requirements) · [Установка](#ru-install) · [Обновление](#ru-update) · [Первый запуск](#ru-first-launch) · [Защита](security.md#russian)

<a id="ru-requirements"></a>

### Требования и совместимость

- Android 7.0 или новее, API 24 и выше.
- Устройство ARM64 с поддержкой ABI `arm64-v8a`.
- API-ключ OpenRouter и интернет для проверки ключа, моделей и сообщений.
- Поддерживаемая блокировка устройства для необязательного системного восстановления PIN в Android 11 и новее.

Минимальный API не означает проверку каждой версии Android или каждого устройства. Текущий пакет прошёл статические проверки выравнивания ELF и ZIP для страниц 4 КиБ и 16 КиБ. Работа на настоящем ARM64-устройстве с ядром 16 КиБ ещё не проверена. Прежний запуск другого пакета через ARM-трансляцию не подтверждает такую работу этого пакета.

<a id="ru-install"></a>

### Получение и установка APK

На странице [Releases](https://github.com/Umichata/tokenlogue/releases) проекта сейчас нет общедоступного Android APK. Используйте APK из текущего комплекта предварительной версии. Уже опубликованный выпуск Linux является другим пакетом.

| Текущая версия Android | Значение |
| --- | --- |
| APK | `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk` |
| Версия | `0.1.0`, versionCode `41` |
| Размер | 56 160 490 байт |
| SHA-256 | `2f7c699960e3967220f526245ca2acbf4335104a141ccf3fa2b8a04dae4709d9` |
| SHA-256 сертификата подписи | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

Перед установкой сверьте APK с файлом `SHA256SUMS` из комплекта. В Linux выполните следующую команду из папки с этими файлами.

```bash
sha256sum --check SHA256SUMS
```

Каждый перечисленный файл должен получить `OK`. Передайте проверенный APK на устройство, откройте его и следуйте установщику Android. Система может попросить разрешить установку из использованного файлового менеджера или браузера. Давайте разрешение только для пакета, которому доверяете. После установки его можно отключить.

<a id="ru-update"></a>

### Обновление совместимой установки

Установите новый APK поверх совместимой прежней версии с тем же идентификатором приложения и сертификатом подписи. Сохраните данные приложения. Удаление приложения и очистка данных не являются обычным шагом обновления и могут сделать зашифрованную переписку невосстановимой.

Если Android отказывает в обновлении, проверьте версию, архитектуру и подпись пакета. Не удаляйте прежнее приложение только для обхода ошибки подписи. Сохраните данные и обратитесь за помощью.

<a id="ru-first-launch"></a>

### Подключение и первый чат

<img src="assets/screenshots/android-start-ru.png" alt="Первый запуск Android" width="320">

Первый запуск Android.

Выберите язык, введите API-ключ OpenRouter и нажмите `Проверить ключ`. Выберите и повторите четырёхзначный PIN приложения, затем сохраните его. Через `+` выберите бесплатный или платный режим, модель и лимиты. Работа с чатами, черновиками и расходами описана в [руководстве пользователя](user-guide.md#russian).

Верхняя левая кнопка открывает панель чатов. Для закрытия выберите чат, нажмите вне панели или используйте Back. Клавиатура может уменьшить место для действий в шапке. Закройте её, чтобы снова показать кнопки переименования и удаления.

### Защита локального профиля

Уход Tokenlogue в фон закрывает доступ. При возвращении введите PIN приложения. Сохранённый черновик восстановится. Разблокировка Android не открывает Tokenlogue автоматически.

На поддерживаемом Android 11 и новее `Забыли PIN?` запрашивает новое системное подтверждение перед сохранением нового PIN приложения. Отмена сохраняет прежний PIN и переписку. Подробнее в разделе [о восстановлении и шифровании](security.md#ru-recovery).

Резервное копирование приложения в Android отключено. Приложение использует интернет и системные возможности аутентификации. Доступ к микрофону не запрашивается. Изменение защиты устройства, удаление приложения и очистка данных могут повлиять на ключи, нужные для чтения защищённой переписки. Одна копия базы не является переносимой резервной копией.

[Руководство пользователя](user-guide.md#russian) · [Защита](security.md#russian) · [Исходные материалы](source-materials.md#russian) · [Tokenlogue](../README.md#russian)
