<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="CHANGELOG.ru.md#russian" title="RU"><img align="right" src="docs/assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="CHANGELOG.md#english" title="EN"><img align="right" src="docs/assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="docs/assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="docs/assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="docs/assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="docs/assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="docs/README.ru.md" title="Карта документации"><img src="docs/assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="docs/user-guide.ru.md" title="Руководство"><img src="docs/assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="docs/providers.ru.md" title="Провайдеры"><img src="docs/assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="docs/analytics.ru.md" title="Статистика"><img src="docs/assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="изменения-версий"></a>

# Изменения версий

<a id="011"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> 0.1.1

### Android Dart 0.1.1+18

[Скачать Tokenlogue Dart 0.1.1+18 для Android ARM64](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk).

У Android Dart отдельный ярлык и собственный профиль. Бюджет платного чата задаётся в валюте провайдера, USD для OpenRouter и RUB для VSEGPT. Настройка, обновление и восстановление PIN описаны в [руководстве Dart](docs/android-dart/README.ru.md).

### Android и Linux на Python

[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1) поставляется для Android ARM64 и Linux x86_64. Предыдущий выпуск [Tokenlogue 0.1.0](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) также доступен.

<a id="изменения-относительно-010"></a>

### Изменения относительно 0.1.0

- Отдельные формы OpenRouter и VSEGPT с компактным списком просмотра **Провайдер**.
- Дневной график токенов разделяет usage API, оценки и неполные или недатированные данные.
- **Ручной выбор** предлагает сервис для каждого нового чата и сохраняет прежние предпочтения сервиса.
- Ошибки каталога показывают конкретную безопасную причину с обновлением списка. VSEGPT сразу открывает платные модели, без отдельного выбора режима.
- Экраны выбора режима и модели прокручиваются общим списком, сохраняя доступ к действиям в низких окнах.
- Проверка сохранённого ключа доступна в режимах OpenRouter и списке моделей VSEGPT. Она обновляет текущий статус без повторного ввода ключа и без генерации.
- Выбор модели с учётом сервиса и сохранение фильтров страниц **Токены** и **Расходы**.
- Раздельные панели USD и RUB и защита текущего просмотра от устаревших результатов загрузки.
- Короткие русские и английские сообщения о ключах, балансах и ошибках.
- Точные названия баланса сервиса, лимита ключа OpenRouter и местного бюджета чата. Неподдерживаемый отдельный лимит ключа VSEGPT не показывается.
- Блок подключения чата с провайдером, безопасной маской общего ключа и переходом к его настройкам.
- Явная смена провайдера существующего чата с проверкой модели и бюджета, сохранением переписки и черновика.
- Общий учёт токенов, отдельные денежные состояния провайдеров и исторические сведения о попытках после смены. Прежнее разрешение на автоматическую платную отправку отзывается.
- Подсказки открытой формы PIN переключаются вместе с языком без переоткрытия.
- Ошибка загрузки каталога при подтверждении цены отличается от подтверждённого отсутствия модели. Сбой не отправляет сообщение и не удаляет черновик.
- Выбранные нативные wheels собственной сборки имеют записанные исходники, патчи и рецепт. libffi в CFFI указана отдельно от libffi Python runtime.
- Обновлённые руководства и примеры четырёх страниц приложения.

Порядок работы описан в руководствах [по чату](docs/user-guide.ru.md), [провайдерам](docs/providers.ru.md) и [статистике](docs/analytics.ru.md). Демонстрационные иллюстрации не подтверждают реальные запросы к сервисам.

<a id="обновление"></a>

### Обновление

Совместимый APK Android с прежней подписью устанавливается поверх приложения с сохранением данных. В Linux закройте старые копии и сохраните доступ к прежнему хранилищу ключей. Перед переносом профиля прочитайте о [защите данных](docs/security.ru.md).

<a id="ограничения"></a>

### Ограничения

Местные оценки токенов и стоимости приблизительны. Баланс может быть недоступен при рабочем ключе чата. Работа нативного ARM64 с ядром 16 КиБ ещё не проверена. Для выбранных новых нативных wheels записаны исходники и собственные сборки. Это не подтверждает задним числом происхождение прежних wheels и не означает полной независимой воспроизводимости. См. [исходные материалы](docs/source-materials.ru.md).
