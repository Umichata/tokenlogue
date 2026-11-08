<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a>&nbsp;<a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android"><img src="docs/assets/ui/buttons/ru-007800957d4f.svg" alt="Android" width="83" height="28"></a>&nbsp;<a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/ru-1b58edc5b8a8.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner.png" alt="Tokenlogue" width="100%">
</h1>

<a id="russian"></a>
<a id="lang-ru"></a>

Общайтесь с моделями OpenRouter на компьютере Linux. Tokenlogue предоставляет компактное пространство для переписки с черновиками, выбором модели и оценкой затрат во время набора.

**<a href="https://github.com/Umichata/tokenlogue/releases" title="Скачать"><img src="docs/assets/ui/buttons/ru-157b95e48686.svg" alt="Скачать" width="112" height="34"></a>** · **<a href="docs/linux-appimage.ru.md#russian" title="Руководство Linux"><img src="docs/assets/ui/buttons/ru-feb543e787e5.svg" alt="Руководство Linux" width="192" height="34"></a>** · **<a href="docs/README.ru.md#russian" title="Все документы"><img src="docs/assets/ui/buttons/ru-e3eb4dff0297.svg" alt="Все документы" width="167" height="34"></a>**

<a href="#ru-install" title="Установка"><img src="docs/assets/ui/buttons/ru-f3b204701c35.svg" alt="Установка" width="129" height="34"></a> · <a href="#ru-chat" title="Первый чат"><img src="docs/assets/ui/buttons/ru-3783f62fda9d.svg" alt="Первый чат" width="139" height="34"></a> · <a href="docs/security.ru.md#russian" title="Защита"><img src="docs/assets/ui/buttons/ru-c71fb64e5880.svg" alt="Защита" width="109" height="34"></a>

<p align="center">
  <img src="docs/assets/ui/feature-panel-ru.svg" alt="Чаты и черновики · локальная оценка · защита переписки" width="100%">
</p>

<a id="ru-screenshots"></a>

## 🖼️ Как выглядит приложение

<a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/ui/frame-top.svg" width="760" alt=""><br>
<img src="docs/assets/screenshots/linux-chat.png" alt="Чат Linux с локальными демонстрационными сообщениями" width="760"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="760" alt=""></a>

Чат Linux с локальными демонстрационными сообщениями.

<a id="ru-install"></a>
## 🚀 Загрузка и запуск

Пакет поставляется как **неподписанная AppImage x86_64**. Нужны процессор x86-64-v2, совместимые библиотеки рабочего стола и видеодрайверы. Базовая версия системных библиотек соответствует Ubuntu 22.04. Обычный запуск использует FUSE, при его отсутствии можно запустить с распаковкой.

Для этой предварительной версии выберите `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` и `RELEASE_SHA256SUMS` на странице <a href="https://github.com/Umichata/tokenlogue/releases" title="Releases">Releases&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Если этой версии нет в списке, её загрузки ещё не опубликованы. [Прежний опубликованный Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) остаётся историческим пакетом с собственными примечаниями к выпуску. На снимке выше показан текущий интерфейс.

Проверьте только выбранную AppImage по её записи в `RELEASE_SHA256SUMS`, как описано в руководстве Linux ниже. Разрешите выполнение и запустите её от обычного пользователя. При обновлении закройте прежние копии перед открытием нового файла. Отдельная установка Python, Flutter или Java и архивы исходников не нужны.

<a href="docs/linux-appimage.ru.md#russian" title="Требования Linux, проверка суммы и запуск"><img src="docs/assets/ui/buttons/ru-9f6a2e3f10a7.svg" alt="Требования Linux, проверка суммы и запуск" width="265" height="50"></a>

<a id="ru-chat"></a>
## 💬 Начало переписки

<p align="center">
  <img src="docs/assets/ui/onboarding-ru.svg" alt="Проверьте ключ OpenRouter, задайте PIN и создайте чат" width="100%">
</p>

Добавьте свой ключ OpenRouter, дождитесь его проверки приложением и задайте PIN. Создайте чат и выберите модель. Черновики сохраняются для каждого чата. Действия переименования и удаления расположены под названием разговора.

Локальная оценка приблизительна. Бюджет чата, лимит ключа OpenRouter и баланс аккаунта — разные величины. Отключение подтверждения платного запроса действует с первого запроса выбранного чата, а лимиты продолжают работать.

<a href="docs/user-guide.ru.md#russian" title="Руководство по чату и затратам"><img src="docs/assets/ui/buttons/ru-fd5aa03e6e8e.svg" alt="Руководство по чату и затратам" width="222" height="50"></a>

## 🛡️ Защита локального профиля

Работающий Secret Service в сеансе рабочего стола хранит защищённые материалы ключей. Сохраните переносимый резервный код, когда приложение предложит его, и храните отдельно от компьютера. PIN и шифрование отдельных полей не шифруют всё устройство. Без необходимых ключей или материалов восстановления нельзя обещать восстановление зашифрованной переписки.

<a href="docs/security.ru.md#russian" title="Защита и восстановление"><img src="docs/assets/ui/buttons/ru-410ec2ccc42f.svg" alt="Защита и восстановление" width="248" height="34"></a> · <a href="docs/source-materials.ru.md#russian" title="Исходники"><img src="docs/assets/ui/buttons/ru-2d17d0436984.svg" alt="Исходники" width="134" height="34"></a> · <a href="packaging/linux/appimage/notices.ru.md#russian" title="Лицензии AppImage"><img src="docs/assets/ui/buttons/ru-6414909e9981.svg" alt="Лицензии AppImage" width="203" height="34"></a> · <a href="LICENSE" title="Лицензия MIT"><img src="docs/assets/ui/buttons/ru-2197b6d8ff17.svg" alt="Лицензия MIT" width="155" height="34"></a>

<a id="ru-docs"></a>

## 🧭 Найдите нужный документ

- **Начало работы**
  - <a href="https://github.com/Umichata/tokenlogue/releases" title="Доступные загрузки"><img src="docs/assets/ui/buttons/ru-d0097b603707.svg" alt="Доступные загрузки" width="205" height="34"></a>.
  - <a href="docs/linux-appimage.ru.md#ru-download" title="Запуск на Linux"><img src="docs/assets/ui/buttons/ru-e54381814faf.svg" alt="Запуск на Linux" width="170" height="34"></a>.
  - <a href="docs/android.ru.md#ru-install" title="Установка на Android"><img src="docs/assets/ui/buttons/ru-620a586e69fe.svg" alt="Установка на Android" width="214" height="34"></a>.
- **Переписка и защита**
  - <a href="docs/user-guide.ru.md#russian" title="Чаты, черновики и лимиты"><img src="docs/assets/ui/buttons/ru-d9bc04ebf60f.svg" alt="Чаты, черновики и лимиты" width="256" height="34"></a>.
  - <a href="docs/security.ru.md#russian" title="PIN, шифрование и восстановление"><img src="docs/assets/ui/buttons/ru-df1f6a03aefa.svg" alt="PIN, шифрование и восстановление" width="198" height="50"></a>.
  - <a href="https://github.com/Umichata/tokenlogue/issues" title="Помощь и обращения"><img src="docs/assets/ui/buttons/ru-cf25a248f6a5.svg" alt="Помощь и обращения" width="217" height="34"></a>.
- **Исходники и лицензии**
  - <a href="docs/source-materials.ru.md#russian" title="Исходные материалы"><img src="docs/assets/ui/buttons/ru-810b0819d2f5.svg" alt="Исходные материалы" width="216" height="34"></a>.
  - <a href="THIRD_PARTY_NOTICES.ru.md#russian" title="Сторонние уведомления"><img src="docs/assets/ui/buttons/ru-52d1a5820da7.svg" alt="Сторонние уведомления" width="237" height="34"></a>.
  - <a href="LICENSE" title="Лицензия MIT"><img src="docs/assets/ui/buttons/ru-2197b6d8ff17.svg" alt="Лицензия MIT" width="155" height="34"></a>.

<a href="docs/README.ru.md#russian" title="Полная карта документации">Полная карта документации&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> также содержит материалы упаковки и историю выпусков.
