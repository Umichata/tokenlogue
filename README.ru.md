<a name="russian"></a>
<a name="lang-ru"></a>
<a name="tokenlogue"></a>

<h1 align="center"><img src="docs/assets/tokenlogue-dart-ru.svg" alt="Tokenlogue Dart для Android · OpenRouter + VSEGPT" width="100%"></h1>

<p align="left">
<a href="README.ru.md" title="RU"><img align="right" src="docs/assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="README.md" title="EN"><img align="right" src="docs/assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="docs/assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="docs/assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
<a href="docs/android-dart/README.ru.md" title="Карта документации"><img src="docs/assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="docs/android-dart/README.ru.md#chat" title="Руководство"><img src="docs/assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="#features" title="Возможности"><img src="docs/assets/ui/buttons/v3-ru-7e64b0b657f6.svg" alt="Возможности" width="126" height="30"></a></p>

**Tokenlogue Dart** — клиент OpenRouter и VSEGPT для Android. Выбирайте сервис и модель для каждого чата. Возвращайтесь к черновику после просмотра токенов или расходов.

[Скачать Tokenlogue Dart 0.1.1+18 для Android ARM64](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk). Пакет Dart устанавливается рядом с Tokenlogue на Python. У каждого приложения свой профиль.

<a name="ru-features"></a>
<a name="features"></a>
<a name="возможности"></a>

## Возможности

- У каждого провайдера свой сохранённый ключ. Для OpenRouter доступны бесплатные и платные модели. У VSEGPT открывается каталог моделей.
- Приложение хранит историю и черновики на устройстве. При отправке сообщения выбранный контекст чата передаётся провайдеру. PIN открывает профиль приложения.
- Статистика использует журнал запросов. Суммы OpenRouter в USD и VSEGPT в RUB показаны отдельно.

<a name="ru-screenshots"></a>
<a name="интерфейс"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Интерфейс Android

Переписка, график токенов по дням и окно бюджета сняты на Android Dart 0.1.1+13.

<img src="docs/assets/ui/frame-top.svg" alt="" width="100%">

| Переписка и черновик | Токены по дням | Бюджет чата |
| --- | --- | --- |
| <a href="docs/android-dart/images/v13/chat-ru.png"><img src="docs/android-dart/images/v13/chat-ru.png" alt="Рабочий чат о поездке и сохранённый черновик" width="215"></a> | <a href="docs/android-dart/images/v13/tokens-filled-ru.png"><img src="docs/android-dart/images/v13/tokens-filled-ru.png" alt="Токены по дням для демонстрационного чата" width="215"></a> | <a href="docs/android-dart/images/v13/budget-ru.png"><img src="docs/android-dart/images/v13/budget-ru.png" alt="Предупреждение об остатке бюджета в рублях перед отправкой запроса" width="215"></a> |

<img src="docs/assets/ui/frame-bottom.svg" alt="" width="100%">

[Все экраны приложения](docs/android-dart/gallery.ru.md)

<a name="ru-start"></a>
<a name="установка-и-обновление"></a>

## Установка и первое подключение

Скачайте Dart APK по ссылке выше, [проверьте SHA-256](docs/android-dart/README.ru.md#apk) и откройте файл на устройстве. Нужен Android 7.0 или новее. В меню приложений он называется **Tokenlogue Dart**. Его можно установить рядом с Python-версией. У каждой версии собственные PIN, ключи и история. Перенос между ними не выполняется автоматически.

<a name="первое-подключение"></a>

Откройте новый профиль, введите ключ выбранного сервиса и нажмите **Проверить ключ**. Задайте и повторите PIN из четырёх цифр. Для обновления откройте APK Dart с тем же сертификатом и большим номером сборки поверх установленной Dart-версии.

<a name="что-означают-суммы"></a>

Бюджет ограничивает выбранный чат. Баланс относится к аккаунту провайдера, а у ключа OpenRouter может быть свой лимит. Местная оценка токенов и стоимости приблизительна. Сохраните PIN. На Android 7–10 он нужен для входа в существующий профиль Dart.

<a name="ru-docs"></a>
<a name="документация"></a>

## Руководства

| Руководство | Содержание |
| --- | --- |
| [Использование приложения](docs/android-dart/README.ru.md) | Провайдеры, чат, лимиты, статистика и восстановление |
| [Сборка Android](apps/android_dart/README.ru.md) | Инструменты, подпись и локальная проверка пакета |
| [Скачать Tokenlogue на Python 0.1.1, APK56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) | Установочный APK для Android ARM64. Открывает профиль Python. |

<a name="исходники-и-лицензии"></a>

[Лицензия Tokenlogue](LICENSE)
