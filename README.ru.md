<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android"><img src="docs/assets/ui/buttons/ru-007800957d4f.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/ru-1b58edc5b8a8.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-ru-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="docs/README.ru.md#ru-preview-status"><img src="docs/assets/ui/buttons/ru-f3b0f21094a4.svg" alt="Скачать" width="86" height="28"></a> <a href="docs/linux-appimage.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="docs/README.ru.md"><img src="docs/assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a> <a href="#ru-install"><img src="docs/assets/ui/buttons/ru-e282b6fdb500.svg" alt="Установка" width="103" height="28"></a> <a href="#ru-chat"><img src="docs/assets/ui/buttons/ru-76bdbff64e0d.svg" alt="Первый чат" width="113" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a></p>

<a id="russian"></a>
<a id="lang-ru"></a>

<a id="ru-preview-status"></a>
> **Начальная предварительная версия 0.1.0 — черновик.** Пока выпуск находится в черновике, пакеты приложения недоступны для публичного скачивания. Публикация выполняется только по прямому указанию владельца проекта.

<h3 align="left">Общайтесь с моделями OpenRouter на компьютере Linux. Tokenlogue предоставляет компактное пространство для переписки с черновиками, выбором модели и оценкой затрат во время набора.</h3>

<a id="ru-screenshots"></a>

<a id="-как-выглядит-приложение"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Как выглядит приложение

<a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/ui/frame-top.svg" width="760" alt=""><br>
<img src="docs/assets/screenshots/linux-chat.png" alt="Чат Linux с локальными демонстрационными сообщениями" width="760"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="760" alt=""></a>

Чат Linux с локальными демонстрационными сообщениями.

<a id="ru-install"></a>
<a id="-загрузка-и-запуск"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Загрузка и запуск

Пакет поставляется как **неподписанная AppImage x86_64**. Нужны процессор x86-64-v2, совместимые библиотеки рабочего стола и видеодрайверы. Базовая версия системных библиотек соответствует Ubuntu 22.04. Обычный запуск использует FUSE, при его отсутствии можно запустить с распаковкой.

В черновике подготовлены [`Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) и [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS). Пока выпуск находится в черновике, ссылки доступны сопровождающим репозитория. Иллюстрация рабочего пространства чата с демонстрационными данными. Точный набор элементов зависит от выбранного чата и доступного места.

Начальная серия предварительных выпусков использует отображаемую версию приложения `0.1.0` до отдельно объявленного официального релиза. Отдельные теги и возрастающие номера сборок идентифицируют подготовленные пакеты.

Проверьте только выбранную AppImage по её записи в `SHA256SUMS`, как описано в руководстве Linux ниже. Разрешите выполнение и запустите её от обычного пользователя. При обновлении закройте прежние копии перед открытием нового файла. Отдельная установка Python, Flutter или Java и архивы исходников не нужны.

<p align="left"><a href="docs/linux-appimage.ru.md#russian"><img src="docs/assets/ui/buttons/ru-e92183a5269f.svg" alt="Требования Linux, проверка суммы и запуск" width="361" height="28"></a></p>

<a id="ru-chat"></a>
<a id="-начало-переписки"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Начало переписки

1. Добавьте свой ключ OpenRouter и дождитесь его проверки приложением.
2. Задайте PIN приложения.
3. Создайте чат и выберите модель.

Черновики сохраняются для каждого чата. Действия переименования и удаления расположены под названием разговора.

Баланс OpenRouter поступает из API аккаунта и виден в бесплатных и платных чатах. Состояние обновления показывает, актуально ли значение. При ошибке оно помечается устаревшим или недоступным, а не заменяется локальным расчётом. Для ручного обновления выберите `Обновить ключ и баланс` в `⋮`. Лимит API-ключа и сохранённый бюджет чата остаются отдельными величинами.

Перед платным запросом, после которого по верхней оценке останется не больше 10% денежного лимита чата, появляется предупреждение. Можно отменить отправку, отправить этот запрос один раз или изменить лимит чата. Отмена сохраняет черновик, а сохранение нового лимита ничего не отправляет. Разовое превышение не повышает сохранённый лимит. Обычные подтверждения можно отключить с первого запроса выбранного чата, но предупреждение о бюджете и остальные ограничения продолжают работать. Оценка стоимости и токенов остаётся приблизительной.

<p align="left"><a href="docs/user-guide.ru.md#russian"><img src="docs/assets/ui/buttons/ru-5938260eb6bd.svg" alt="Руководство по чату и затратам" width="269" height="28"></a></p>

<a id="-защита-локального-профиля"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Защита локального профиля

Работающий Secret Service в сеансе рабочего стола хранит защищённые материалы ключей. Сохраните переносимый резервный код, когда приложение предложит его, и храните отдельно от компьютера. PIN и шифрование отдельных полей не шифруют всё устройство. Без необходимых ключей или материалов восстановления нельзя обещать восстановление зашифрованной переписки.

Готовый пакет скачивается отдельно от исходников. Архив проекта из `PROVENANCE.json` соответствует поставленной сборке, а `Tokenlogue-0.1.0-dependency-sources.tar.gz` объединяет идентифицированные сторонние материалы. Руководство по исходникам объясняет состав и оставшиеся ограничения связи некоторых нативных бинарников с исходниками. Наличие архива или лицензии само по себе не доказывает происхождение wheel.

<p align="left"><a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-28527b1f2b04.svg" alt="Защита и восстановление" width="222" height="28"></a> <a href="docs/source-materials.ru.md#russian"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="packaging/linux/appimage/notices.ru.md#russian"><img src="docs/assets/ui/buttons/ru-85ece10d5cbe.svg" alt="Лицензии AppImage" width="177" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></p>

<a id="ru-docs"></a>

<a id="-найдите-нужный-документ"></a>
<a id="найдите-нужный-документ"></a>
<a id="-документация"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Документация

<table>
<tr><th align="left">Раздел</th><th align="left">Документы</th></tr>
<tr>
<td><a id="начало-работы"></a><strong>Начало работы</strong></td>
<td><a href="docs/README.ru.md#ru-preview-status" title="Загрузки"><img src="docs/assets/ui/buttons/ru-f0e4eb0b92d5.svg" alt="Загрузки" width="94" height="28"></a> <a href="docs/linux-appimage.ru.md#ru-download" title="Запуск Linux"><img src="docs/assets/ui/buttons/ru-4b91e607dca0.svg" alt="Запуск Linux" width="122" height="28"></a> <a href="docs/android.ru.md#ru-install" title="Установка Android"><img src="docs/assets/ui/buttons/ru-0abdbebf204e.svg" alt="Установка Android" width="166" height="28"></a></td>
</tr>
<tr>
<td><a id="переписка-и-защита"></a><strong>Переписка и защита</strong></td>
<td><a href="docs/user-guide.ru.md#russian" title="Руководство"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="docs/security.ru.md#russian" title="Защита"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues" title="Помощь"><img src="docs/assets/ui/buttons/ru-9079b2556a7e.svg" alt="Помощь" width="87" height="28"></a></td>
</tr>
<tr>
<td><a id="исходники-и-лицензии"></a><strong>Исходники и лицензии</strong></td>
<td><a href="docs/source-materials.ru.md#russian" title="Исходники"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="THIRD_PARTY_NOTICES.ru.md#russian" title="Уведомления"><img src="docs/assets/ui/buttons/ru-775331545a3f.svg" alt="Уведомления" width="127" height="28"></a> <a href="LICENSE" title="Лицензия MIT"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></td>
</tr>
</table>

Полная карта документации также содержит материалы упаковки и актуальное руководство по исходным материалам.
