<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="android.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="android.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="user-guide.ru.md" title="Руководство"><img src="assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="providers.ru.md" title="Провайдеры"><img src="assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="analytics.ru.md" title="Статистика"><img src="assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="tokenlogue-для-android"></a>

# Tokenlogue для Android (Python)


> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** содержит APK версии на Python для Android ARM64 (сборка 56) и настольный bundle Linux x86_64. Перед установкой проверьте требования платформы и сумму скачанного файла.


[Android Dart 0.1.1+18](https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md) можно установить рядом с версией на Python. У каждого приложения свои PIN, ключи провайдеров и чаты. Для обновления выберите APK того же приложения (Python или Dart).

<a id="требования"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Требования

- Android 7.0 / API 24 или новее и поддержка ARM64 `arm64-v8a`.
- Ключ аккаунта OpenRouter или VSEGPT и интернет для моделей и сообщений.
- Поддерживаемая блокировка устройства для системного восстановления Android 11 и новее.

Минимальный API не означает проверку каждой версии Android. Статические проверки ELF и ZIP учитывают выравнивание 4 и 16 КиБ. Работа на настоящем ARM64-устройстве с ядром 16 КиБ ещё не проверена.

<a id="ru-install"></a>
<a id="ru-local-package"></a>
<a id="установка-android-011"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Установка Android 0.1.1

Скачайте `Tokenlogue-0.1.1-android-arm64-v8a-v56.apk` со страницы [0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1). APK служит установщиком. Для запуска приложения исходные архивы не нужны.

| Параметр | Значение |
| --- | --- |
| Файл | `Tokenlogue-0.1.1-android-arm64-v8a-v56.apk` |
| Версия | 0.1.1, versionCode 56 |
| Архитектура | ARM64, `arm64-v8a` |
| Размер | 56 543 774 байт |
| SHA-256 | `df69735b56c5f4d5da73859aa5f276f39c73d9d43526226175643beae316d6ec` |
| SHA-256 сертификата | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

В папке загрузки проверьте выбранный файл.

```bash
printf '%s  %s\n' \
  'df69735b56c5f4d5da73859aa5f276f39c73d9d43526226175643beae316d6ec' \
  'Tokenlogue-0.1.1-android-arm64-v8a-v56.apk' | sha256sum --check -
```

Продолжайте только после `OK` для указанного APK. Откройте проверенный файл на Android и подтвердите установку. Разрешайте установку выбранному браузеру или файловому менеджеру только при доверии к пакету. После установки разрешение можно отключить. Если Play Protect сообщает об опасном приложении, остановитесь и [сообщите о предупреждении](https://github.com/Umichata/tokenlogue/issues).

<a id="ru-published-preview"></a>
<a id="прежний-preview"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Предыдущий выпуск

[Tokenlogue 0.1.0](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) остаётся отдельным прежним выпуском. Его APK не является новой версией. Правила совместимого обновления приведены ниже.

<a id="обновление-без-удаления-данных"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Обновление без удаления данных

Установите совместимый новый APK поверх приложения. Идентификатор и сертификат подписи должны сохраняться, а versionCode должен расти.

Не удаляйте приложение и не очищайте данные ради обновления. Можно потерять ключи зашифрованной переписки. При отказе из-за подписи или версии сохраните прежнюю установку и проверьте пакет.

<a id="начало-работы-с-011"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Начало работы с 0.1.1

Выполните [первое подключение](user-guide.ru.md#ru-first-connection), чтобы добавить один сервис и создать PIN. Другой ключ можно добавить позже через [Провайдеры](providers.ru.md). Для профиля только с VSEGPT ключ OpenRouter не нужен.

Нижняя навигация открывает **Главную**, **Провайдеры**, **Токены** и **Расходы**. Back возвращает со вспомогательной страницы на Главную. Отдельная кнопка чатов открывает панель разговоров. Закройте её нажатием вне панели или кнопкой Back. Для доступа к действиям в шапке при нехватке места уберите клавиатуру.

<a id="доступ-и-восстановление"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Доступ и восстановление

Уход в фон блокирует приложение. При возвращении введите PIN, чтобы восстановить сохранённый черновик. Разблокировка Android не открывает Tokenlogue автоматически.

На поддерживаемом Android 11 и новее **Забыли PIN?** запрашивает новое подтверждение устройства перед сохранением нового PIN приложения. Отмена сохраняет прежний PIN. См. [защиту и восстановление](security.ru.md#ru-recovery).

Резервное копирование Android отключено. Доступ к микрофону не запрашивается. Одна копия базы не содержит отдельного защищённого ключа.
