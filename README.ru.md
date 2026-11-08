<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="docs/README.ru.md" title="Карта документации"><img src="docs/assets/ui/buttons/ru-be11dde003f4.svg" alt="Карта документации" width="207" height="38"></a> <a href="https://github.com/Umichata/tokenlogue/blob/main/README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android"><img src="docs/assets/ui/buttons/ru-007800957d4f.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/ru-1b58edc5b8a8.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-ru-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases"><img src="docs/assets/ui/buttons/ru-f3b0f21094a4.svg" alt="Скачать" width="86" height="28"></a> <a href="docs/linux-appimage.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="#ru-install"><img src="docs/assets/ui/buttons/ru-e282b6fdb500.svg" alt="Установка" width="103" height="28"></a> <a href="#ru-chat"><img src="docs/assets/ui/buttons/ru-76bdbff64e0d.svg" alt="Первый чат" width="113" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a></p>

<a id="russian"></a>
<a id="lang-ru"></a>

Общайтесь с моделями OpenRouter на компьютере Linux. Tokenlogue предоставляет компактное пространство для переписки с черновиками, выбором модели и оценкой затрат во время набора.

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

Для этой предварительной версии выберите `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` и `RELEASE_SHA256SUMS` на странице <a href="https://github.com/Umichata/tokenlogue/releases" title="Releases">Releases&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Если этой версии нет в списке, её загрузки ещё не опубликованы. [Прежний опубликованный Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) остаётся историческим пакетом с собственными примечаниями к выпуску. На снимке выше показан текущий интерфейс.

Проверьте только выбранную AppImage по её записи в `RELEASE_SHA256SUMS`, как описано в руководстве Linux ниже. Разрешите выполнение и запустите её от обычного пользователя. При обновлении закройте прежние копии перед открытием нового файла. Отдельная установка Python, Flutter или Java и архивы исходников не нужны.

<p align="left"><a href="docs/linux-appimage.ru.md#russian"><img src="docs/assets/ui/buttons/ru-e92183a5269f.svg" alt="Требования Linux, проверка суммы и запуск" width="361" height="28"></a></p>

<a id="ru-chat"></a>
<a id="-начало-переписки"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Начало переписки

1. Добавьте свой ключ OpenRouter и дождитесь его проверки приложением.
2. Задайте PIN приложения.
3. Создайте чат и выберите модель.

Черновики сохраняются для каждого чата. Действия переименования и удаления расположены под названием разговора.

Локальная оценка приблизительна. Бюджет чата, лимит ключа OpenRouter и баланс аккаунта — разные величины. Отключение подтверждения платного запроса действует с первого запроса выбранного чата, а лимиты продолжают работать.

<p align="left"><a href="docs/user-guide.ru.md#russian"><img src="docs/assets/ui/buttons/ru-5938260eb6bd.svg" alt="Руководство по чату и затратам" width="269" height="28"></a></p>

<a id="-защита-локального-профиля"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Защита локального профиля

Работающий Secret Service в сеансе рабочего стола хранит защищённые материалы ключей. Сохраните переносимый резервный код, когда приложение предложит его, и храните отдельно от компьютера. PIN и шифрование отдельных полей не шифруют всё устройство. Без необходимых ключей или материалов восстановления нельзя обещать восстановление зашифрованной переписки.

<p align="left"><a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-28527b1f2b04.svg" alt="Защита и восстановление" width="222" height="28"></a> <a href="docs/source-materials.ru.md#russian"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="packaging/linux/appimage/notices.ru.md#russian"><img src="docs/assets/ui/buttons/ru-85ece10d5cbe.svg" alt="Лицензии AppImage" width="177" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></p>

<a id="ru-docs"></a>

<a id="-найдите-нужный-документ"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Найдите нужный документ

<a id="начало-работы"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Начало работы

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases"><img src="docs/assets/ui/buttons/ru-840902d46c65.svg" alt="Загрузки" width="94" height="28"></a> <a href="docs/linux-appimage.ru.md#ru-download"><img src="docs/assets/ui/buttons/ru-4b91e607dca0.svg" alt="Запуск Linux" width="122" height="28"></a> <a href="docs/android.ru.md#ru-install"><img src="docs/assets/ui/buttons/ru-0abdbebf204e.svg" alt="Установка Android" width="166" height="28"></a></p>

<a id="переписка-и-защита"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Переписка и защита

<p align="left"><a href="docs/user-guide.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues"><img src="docs/assets/ui/buttons/ru-9079b2556a7e.svg" alt="Помощь" width="87" height="28"></a></p>

<a id="исходники-и-лицензии"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники и лицензии

<p align="left"><a href="docs/source-materials.ru.md#russian"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="THIRD_PARTY_NOTICES.ru.md#russian"><img src="docs/assets/ui/buttons/ru-775331545a3f.svg" alt="Уведомления" width="127" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></p>

Полная карта документации также содержит материалы упаковки и историю выпусков.
