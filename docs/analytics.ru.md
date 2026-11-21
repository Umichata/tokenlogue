<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="analytics.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="analytics.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="user-guide.ru.md" title="Руководство"><img src="assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="providers.ru.md" title="Провайдеры"><img src="assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="analytics.ru.md" title="Статистика"><img src="assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="токены-и-дневные-расходы"></a>

# Токены и дневные расходы


> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** содержит два APK для Android ARM64 (Python +56 и Dart +18) и комплект для Linux x86_64. Перед установкой проверьте требования платформы и сумму скачанного файла.


<a id="область-и-фильтры"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Область и фильтры

**Токены** и **Расходы** читают журнал запросов сохранённых чатов этого устройства. Активность других приложений не включается. Удаление чата также удаляет его местную статистику.

Один чат может содержать запросы к обоим сервисам. Каждая попытка сохраняет провайдера, модель, валюту и достоверно известную дату отправки. Смена текущего подключения не переписывает прежнюю статистику. USD и RUB остаются раздельными и после возврата к ранее использованному провайдеру.

Каждая страница сохраняет собственный выбор в списке **Провайдер**, период и совместимый фильтр модели. В списке есть **Все**, **OpenRouter** и **VSEGPT**. Доступны **7 дней**, **30 дней** и **Всё время**. Просмотр сервиса не меняет ключ, провайдера новых чатов или сервис открытого разговора.

Список моделей учитывает выбранный сервис и период. Одинаковый ID модели в OpenRouter и VSEGPT остаётся двумя вариантами. При смене провайдера несовместимый выбор модели сбрасывается.

<a id="токены"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Токены

| Linux | Эмулятор Android |
| --- | --- |
| <a href="assets/screenshots/v011-55-linux-daily-tokens-ru.png"><img src="assets/ui/frame-top.svg" alt="" width="560"><br><img src="assets/screenshots/v011-55-linux-daily-tokens-ru.png" alt="Статистика токенов с фильтром провайдера в Linux" width="560"><br><img src="assets/ui/frame-bottom.svg" alt="" width="560"></a> | <a href="assets/screenshots/v011-55-android-daily-tokens-ru.png"><img src="assets/ui/frame-top.svg" alt="" width="300"><br><img src="assets/screenshots/v011-55-android-daily-tokens-ru.png" alt="Статистика токенов с фильтром провайдера в эмуляторе Android" width="300"><br><img src="assets/ui/frame-bottom.svg" alt="" width="300"></a> |

*Демонстрационный журнал, не оплаченные запросы. Кадры Android сняты в эмуляторе.*

График **Токены по дням** группирует сохранённые попытки по известной дате отправки в показанном часовом поясе с теми же фильтрами, что и таблица моделей. Цвета отличают значения API от местных оценок. Нажмите день или используйте кнопки выбора дня, чтобы увидеть входные, выходные и общие токены, их источник и неполноту. Длинная история просматривается окном. Запрос с неизвестным количеством токенов отличается от дня без запросов. Отсутствующее общее количество не восстанавливается как значение API.

Просмотрите выбранный день в [Linux](assets/screenshots/v011-55-linux-daily-tokens-day-ru.png) или в [эмуляторе Android](assets/screenshots/v011-55-android-selected-token-day-ru.png).

Страница показывает отдельные итоги провайдеров, число запросов, входные, выходные и общие токены по данным API и таблицу моделей. Полосы популярных моделей учитывают выбранные фильтры.

Данные API, местные оценки и отсутствие сведений разделены. Оценки не увеличивают сумму токенов API. Сведения о кэше и рассуждениях не прибавляются повторно. Известные токены видны даже при неизвестной стоимости. Поля API не являются независимой проверкой токенизатора. Цены за символы не пересчитываются в токены.

Исторические запросы без достоверной даты отправки доступны только за **Всё время**. Им не присваивается выдуманный день. Пустой результат означает отсутствие сохранённых запросов по выбранным условиям.

<a id="дневные-расходы"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Дневные расходы

| Linux | Эмулятор Android |
| --- | --- |
| <a href="assets/screenshots/v011-55-linux-spending-ru.png"><img src="assets/ui/frame-top.svg" alt="" width="560"><br><img src="assets/screenshots/v011-55-linux-spending-ru.png" alt="Дневные расходы с отдельными валютами в Linux" width="560"><br><img src="assets/ui/frame-bottom.svg" alt="" width="560"></a> | <a href="assets/screenshots/v011-55-android-spending-ru.png"><img src="assets/ui/frame-top.svg" alt="" width="300"><br><img src="assets/screenshots/v011-55-android-spending-ru.png" alt="Дневные расходы с отдельными валютами в эмуляторе Android" width="300"><br><img src="assets/ui/frame-bottom.svg" alt="" width="300"></a> |

*Демонстрационный журнал, не оплаченные запросы. Кадры Android сняты в эмуляторе.*

В примерах выбраны **Все**, **7 дней** и **Все модели**. У каждой валюты своя панель и шкала. Прокрутите страницу для сравнения панелей и таблиц по датам. [Дополнительный кадр Linux](assets/screenshots/v011-55-linux-spending-table-ru.png) показывает другую часть того же демонстрационного журнала.

В режиме **Все** показаны отдельные панели OpenRouter в USD и VSEGPT в RUB. При выборе одного сервиса остаётся только он. Общей денежной суммы, единой валютной шкалы и пересчёта курса нет.

В каждой панели есть дневной график, подтверждённая сумма датированных расходов, средний расход за день и таблица даты, суммы и валюты. Оценки имеют отдельный ряд и итог. Дни без запросов показывают ноль. Неизвестная стоимость помечает сумму как неполную и не превращается в бесплатный запрос.

Группировка использует указанный на странице часовой пояс и исходное время отправки. Позднее уточнение учёта остаётся на том же дне. Недатированные исторические суммы вынесены отдельно и не участвуют в графике и среднем за день.

Это местная записанная активность. Она не заменяет выписку и биллинг сервиса. Повтор, дошедший до провайдера, считается новым запросом. [Бюджет чата](user-guide.ru.md) и [балансы провайдеров](providers.ru.md) описывают другие значения.
