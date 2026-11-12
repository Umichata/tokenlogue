<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android"><img src="docs/assets/ui/buttons/ru-189001d7bb97.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/ru-66f2899ff23a.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-ru-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk" title="Скачать APK"><img src="docs/assets/ui/buttons/ru-f3b0f21094a4.svg" alt="Скачать" width="86" height="28"></a> <a href="docs/android.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="docs/README.ru.md"><img src="docs/assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a> <a href="#ru-install"><img src="docs/assets/ui/buttons/ru-e282b6fdb500.svg" alt="Установка" width="103" height="28"></a> <a href="#ru-chat"><img src="docs/assets/ui/buttons/ru-76bdbff64e0d.svg" alt="Первый чат" width="113" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a></p>

<a id="russian"></a>
<a id="lang-ru"></a>

<a id="ru-preview-status"></a>
> **[0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9)** · Доступна для Android. Скачайте пакет кнопкой выше и откройте [инструкцию установки](docs/android.ru.md#ru-install).

<h3 align="left">Общайтесь с моделями OpenRouter на телефоне или планшете Android. Tokenlogue объединяет чаты, черновики и выбор модели в одном мобильном рабочем пространстве.</h3>

<a id="ru-screenshots"></a>

<a id="-как-выглядит-приложение"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Интерфейс

<p align="center">
<a href="docs/assets/screenshots/android-start-ru.png"><img src="docs/assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="docs/assets/screenshots/android-start-ru.png" alt="Экран подключения OpenRouter в Android." width="320"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="320" alt=""></a>
</p>

<p align="center">Экран подключения OpenRouter в Android.</p>

<a id="ru-install"></a>
<a id="-установка-и-обновление"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Установка

Tokenlogue для Android поставляется как **APK ARM64** для **Android 7.0 / API 24 или новее**. Скачайте [APK для Android](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) и [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) из [0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9).

Проверьте APK по `SHA256SUMS`, откройте его и следуйте подсказкам установки Android. Play Protect может предложить проверку незнакомого пакета. Для обновления устанавливайте совместимое приложение с прежним сертификатом поверх существующего, сохраняя его данные. Для запуска не нужны Python, Flutter и архивы исходников.

<p align="left"><a href="docs/android.ru.md#russian"><img src="docs/assets/ui/buttons/ru-28ca0bed29c8.svg" alt="Подробная установка Android" width="252" height="28"></a></p>

<a id="ru-chat"></a>
<a id="-начало-переписки"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Первый запуск

1. Добавьте API-ключ OpenRouter и дождитесь его проверки через сеть.
2. Задайте PIN приложения и сохраните предложенные для платформы сведения восстановления.
3. Создайте чат, выберите модель и напишите сообщение.

Для каждого разговора сохраняются черновик и выбранная модель. Баланс аккаунта OpenRouter обновляется после завершения отправленного запроса; ручное обновление доступно в меню состояния ключа. Баланс, лимит API-ключа и бюджет чата остаются отдельными величинами. При ошибке обновления значение помечается устаревшим или недоступным.

Перед платным запросом, после которого может остаться 10% лимита чата или меньше, предупреждение предлагает отмену, разовую отправку или изменение лимита. Отмена сохраняет черновик. Сохранение лимита ничего не отправляет, а разовое разрешение не повышает сохранённый лимит. Предупреждение действует и при отключённых обычных подтверждениях. Оценки токенов и стоимости приблизительны.

<p align="left"><a href="docs/user-guide.ru.md#russian"><img src="docs/assets/ui/buttons/ru-74950865d17e.svg" alt="Руководство по чатам" width="193" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-872ae26a2897.svg" alt="PIN, шифрование и восстановление Android" width="359" height="28"></a></p>

<a id="-что-защищено"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Защита и восстановление

PIN и шифрование защищают отдельные локальные поля переписки, а не всё устройство. Для восстановления в Android нужны поддерживаемая и настроенная блокировка экрана и доступ к исходному защищённому ключу шифрования. Удаление локального профиля необратимо удаляет историю и черновики; оно не удаляет аккаунт OpenRouter и не возвращает кредиты.

При отправке сообщения выбранное содержимое разговора передаётся OpenRouter и провайдеру модели. Исходники, материалы зависимостей и лицензии описаны отдельно.

<p align="left"><a href="docs/source-materials.ru.md#russian"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="THIRD_PARTY_NOTICES.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7e77b0d7b2f0.svg" alt="Сторонние лицензии" width="182" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></p>

<a id="ru-docs"></a>

<a id="-найдите-нужный-документ"></a>
<a id="найдите-нужный-документ"></a>
<a id="-документация"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Документация

<table>
<tr><th align="left">Раздел</th><th align="left">Документы</th></tr>
<tr>
<td><a id="начало-работы"></a><strong>Установка</strong></td>
<td><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9" title="Загрузки"><img src="docs/assets/ui/buttons/ru-f0e4eb0b92d5.svg" alt="Загрузки" width="94" height="28"></a> <a href="docs/android.ru.md#ru-install" title="Установка Android"><img src="docs/assets/ui/buttons/ru-0abdbebf204e.svg" alt="Установка Android" width="166" height="28"></a> <a href="docs/linux-appimage.ru.md#ru-download" title="Запуск Linux"><img src="docs/assets/ui/buttons/ru-4b91e607dca0.svg" alt="Запуск Linux" width="122" height="28"></a></td>
</tr>
<tr>
<td><a id="переписка-и-защита"></a><strong>Чаты и безопасность</strong></td>
<td><a href="docs/user-guide.ru.md#russian" title="Руководство"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="docs/security.ru.md#russian" title="Защита"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues" title="Помощь"><img src="docs/assets/ui/buttons/ru-9079b2556a7e.svg" alt="Помощь" width="87" height="28"></a></td>
</tr>
<tr>
<td><a id="исходники-и-лицензии"></a><strong>Исходники и лицензии</strong></td>
<td><a href="docs/source-materials.ru.md#russian" title="Исходники"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="THIRD_PARTY_NOTICES.ru.md#russian" title="Уведомления"><img src="docs/assets/ui/buttons/ru-775331545a3f.svg" alt="Уведомления" width="127" height="28"></a> <a href="LICENSE" title="Лицензия MIT"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></td>
</tr>
</table>
