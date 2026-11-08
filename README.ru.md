<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="docs/README.ru.md" title="Карта документации"><img src="docs/assets/ui/buttons/ru-be11dde003f4.svg" alt="Карта документации" width="207" height="38"></a> <a href="https://github.com/Umichata/tokenlogue/blob/main/README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android"><img src="docs/assets/ui/buttons/ru-189001d7bb97.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/ru-66f2899ff23a.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-ru-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases"><img src="docs/assets/ui/buttons/ru-f3b0f21094a4.svg" alt="Скачать" width="86" height="28"></a> <a href="docs/android.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="#ru-install"><img src="docs/assets/ui/buttons/ru-e282b6fdb500.svg" alt="Установка" width="103" height="28"></a> <a href="#ru-chat"><img src="docs/assets/ui/buttons/ru-76bdbff64e0d.svg" alt="Первый чат" width="113" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a></p>

<a id="russian"></a>
<a id="lang-ru"></a>

Общайтесь с моделями OpenRouter на телефоне или планшете Android. Tokenlogue объединяет чаты, черновики и выбор модели в одном мобильном рабочем пространстве.

<a id="ru-screenshots"></a>

<a id="-как-выглядит-приложение"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Как выглядит приложение

<table>
<tr><th>🔑 Первое подключение</th><th>💬 Переписка</th></tr>
<tr>
<td align="center"><a href="docs/assets/screenshots/android-start-ru.png"><img src="docs/assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="docs/assets/screenshots/android-start-ru.png" alt="Подключение ключа OpenRouter на Android" width="320"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="320" alt=""></a></td>
<td align="center"><a href="docs/assets/screenshots/android-chat-ru.png"><img src="docs/assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="docs/assets/screenshots/android-chat-ru.png" alt="Рабочий чат Tokenlogue на планшете Android" width="320"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="320" alt=""></a></td>
</tr>
</table>

Рабочий чат Tokenlogue на планшете Android.

<a id="ru-install"></a>
<a id="-установка-и-обновление"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Установка и обновление

Нужен **Android 7.0 / API 24 или новее с ARM64**. Поддерживаемый минимум не означает проверку каждой версии Android. Статические проверки 16 КиБ пройдены, но работа на нативном ARM64-устройстве с ядром 16 КиБ пока не проверена.

Для этой предварительной версии выберите `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk` и `RELEASE_SHA256SUMS` на странице <a href="https://github.com/Umichata/tokenlogue/releases" title="Releases">Releases&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Если этой версии нет в списке, её загрузки ещё не опубликованы. Проверьте только APK по его записи в манифесте, как описано в руководстве Android ниже. Для запуска Tokenlogue не нужны отдельная установка Python или Flutter и архивы исходников.

Разрешите установку выбранному файловому менеджеру или браузеру, откройте проверенный APK и следуйте подсказкам Android. Для обновления устанавливайте его поверх совместимой прежней версии с тем же сертификатом. Не удаляйте приложение и не очищайте данные как обычный шаг обновления.

<p align="left"><a href="docs/android.ru.md#russian"><img src="docs/assets/ui/buttons/ru-28ca0bed29c8.svg" alt="Подробная установка Android" width="252" height="28"></a></p>

<a id="ru-chat"></a>
<a id="-начало-переписки"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Начало переписки

1. Добавьте собственный ключ OpenRouter и дождитесь его проверки через сеть.
2. Задайте PIN приложения.
3. Создайте чат и выберите модель.

Черновик и выбор модели сохраняются для этого разговора. Действия чата позволяют переименовать или удалить его.

Бюджет чата, лимит ключа OpenRouter и баланс аккаунта различаются. Оценка токенов и стоимости приблизительна. Отключение подтверждения платного запроса действует с первого запроса выбранного чата, а лимиты продолжают работать.

<p align="left"><a href="docs/user-guide.ru.md#russian"><img src="docs/assets/ui/buttons/ru-74950865d17e.svg" alt="Руководство по чатам" width="193" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-872ae26a2897.svg" alt="PIN, шифрование и восстановление Android" width="359" height="28"></a></p>

<a id="-что-защищено"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Что защищено

Шифруются отдельные локальные поля переписки, а не всё устройство. Для системного восстановления нужны поддерживаемая и настроенная блокировка Android и доступ к исходному защищённому ключу шифрования. Удаление локального профиля необратимо и не возвращает средства и не удаляет аккаунт OpenRouter.

<p align="left"><a href="docs/source-materials.ru.md#russian"><img src="docs/assets/ui/buttons/ru-f5984adb7290.svg" alt="Исходники и ограничения происхождения" width="347" height="28"></a> <a href="THIRD_PARTY_NOTICES.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7e77b0d7b2f0.svg" alt="Сторонние лицензии" width="182" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></p>

<a id="ru-docs"></a>

<a id="-найдите-нужный-документ"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Найдите нужный документ

<a id="начало-работы"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Начало работы

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases"><img src="docs/assets/ui/buttons/ru-840902d46c65.svg" alt="Загрузки" width="94" height="28"></a> <a href="docs/android.ru.md#ru-install"><img src="docs/assets/ui/buttons/ru-0abdbebf204e.svg" alt="Установка Android" width="166" height="28"></a> <a href="docs/linux-appimage.ru.md#ru-download"><img src="docs/assets/ui/buttons/ru-4b91e607dca0.svg" alt="Запуск Linux" width="122" height="28"></a></p>

<a id="переписка-и-защита"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Переписка и защита

<p align="left"><a href="docs/user-guide.ru.md#russian"><img src="docs/assets/ui/buttons/ru-7c519bac3145.svg" alt="Руководство" width="121" height="28"></a> <a href="docs/security.ru.md#russian"><img src="docs/assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues"><img src="docs/assets/ui/buttons/ru-9079b2556a7e.svg" alt="Помощь" width="87" height="28"></a></p>

<a id="исходники-и-лицензии"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники и лицензии

<p align="left"><a href="docs/source-materials.ru.md#russian"><img src="docs/assets/ui/buttons/ru-2d110f2e4021.svg" alt="Исходники" width="108" height="28"></a> <a href="THIRD_PARTY_NOTICES.ru.md#russian"><img src="docs/assets/ui/buttons/ru-775331545a3f.svg" alt="Уведомления" width="127" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/ru-b92966969a04.svg" alt="Лицензия MIT" width="129" height="28"></a></p>

Полная карта документации также содержит материалы упаковки и историю выпусков.
