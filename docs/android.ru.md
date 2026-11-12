<p align="left">
<a href="android.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="android.md" title="English"><img align="right" src="assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Tokenlogue для Android

<a id="russian"></a>
<a id="lang-ru"></a>

<a id="ru-preview-status"></a>
> **0.1.0 Preview · prerelease.** [Скачать опубликованную версию](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9).

Tokenlogue позволяет общаться с моделями OpenRouter на телефоне или планшете Android ARM64. Есть русский и английский интерфейс, отдельные черновики чатов и компоновка, которая учитывает доступное место.

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk" title="Скачать APK"><img src="assets/ui/buttons/ru-840902d46c65.svg" alt="Скачать APK" width="94" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS">Контрольные суммы (SHA256SUMS)</a></p>

<p align="left"><a href="#ru-requirements"><img src="assets/ui/buttons/ru-c8c1bdfd645d.svg" alt="Требования" width="114" height="28"></a> <a href="#ru-install"><img src="assets/ui/buttons/ru-e282b6fdb500.svg" alt="Установка" width="103" height="28"></a> <a href="#ru-update"><img src="assets/ui/buttons/ru-fee57eb0b9e5.svg" alt="Обновление" width="117" height="28"></a> <a href="#ru-first-launch"><img src="assets/ui/buttons/ru-50fa519ff78f.svg" alt="Первый запуск" width="138" height="28"></a> <a href="security.ru.md#russian"><img src="assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a></p>

<a id="ru-requirements"></a>

<a id="-требования-и-совместимость"></a>
<a id="требования-и-совместимость"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Требования

- Android 7.0 или новее, API 24 и выше.
- Устройство ARM64 с поддержкой ABI `arm64-v8a`.
- API-ключ OpenRouter и интернет для проверки ключа, моделей и сообщений.
- Поддерживаемая блокировка устройства для необязательного системного восстановления PIN в Android 11 и новее.

Совместимость с устройствами, использующими страницы памяти 16 КиБ, пока не подтверждена.

<a id="ru-install"></a>

<a id="-получение-и-установка-apk"></a>
<a id="получение-и-установка-apk"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Установка

Скачайте [APK для Android](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) и [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) из опубликованного выпуска **Tokenlogue 0.1.0 Preview**. APK — установочный файл; архивы GitHub «Source code» не являются установщиками Android.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Пакет Android | Сведения |
| --- | --- |
| APK | [`Tokenlogue-0.1.0-android-arm64-v8a-v43.apk`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) |
| Версия | `0.1.0`, versionCode `43` |
| SHA-256 | `1e3ec65aaf1863eb50257aa4c090ca5fdf0b6b2c637c415d5b02056a2cf941f5` |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Перед установкой сверьте только выбранный APK с `SHA256SUMS`. Сохраните оба файла в одной папке. На компьютере используйте Bash и средства SHA-256, чтобы выполнить из этой папки следующую команду.
```bash
set -o pipefail
file='Tokenlogue-0.1.0-android-arm64-v8a-v43.apk'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Продолжайте установку, только если проверка завершилась с `OK`. При несовпадении скачайте пакет заново. Контрольная сумма подтверждает целостность файла, но не заменяет подпись издателя.

Архивы исходников и средства сборки скачиваются отдельно. Для установки и запуска Tokenlogue они не нужны.

Передайте проверенный APK на устройство, откройте его и следуйте установщику Android. Система может попросить разрешить установку из использованного файлового менеджера или браузера. Давайте разрешение только для пакета, которому доверяете. После установки его можно отключить.

<a id="ru-install-warning"></a>
<a id="google-play-protect-при-установке"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Проверка Google Play

Google Play Защита может предложить сканирование незнакомого APK. Нажмите `Проверить` и следуйте результату. Если обнаружено вредоносное приложение, остановите установку и [сообщите о предупреждении](https://github.com/Umichata/tokenlogue/issues). Подпись APK не означает одобрения Google. Подробнее в [руководстве Google по предупреждениям](https://developers.google.com/android/play-protect/warning-dev-guidance).

<a id="ru-home-screen"></a>
<a id="разместить-tokenlogue-на-главном-экране"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Значок на главном экране

Откройте список приложений, найдите Tokenlogue, удерживайте его значок и перетащите на главный экран. Автоматическое размещение зависит от лаунчера и его настроек. Если приложения нет и в общем списке, [сообщите о проблеме](https://github.com/Umichata/tokenlogue/issues), указав модель устройства, версию Android и лаунчер.

<a id="ru-update"></a>

<a id="-обновление-совместимой-установки"></a>
<a id="обновление-совместимой-установки"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Обновление

Установите новый APK поверх совместимой прежней версии с тем же идентификатором приложения и сертификатом подписи. Сохраните данные приложения. Предварительные сборки используют отображаемую версию `0.1.0`. Для совместимого обновления нужен больший versionCode и тот же сертификат подписи. Удаление приложения и очистка данных не являются обычным шагом обновления и могут сделать зашифрованную переписку невосстановимой.

Если Android отказывает в обновлении, проверьте версию, архитектуру и подпись пакета. Не удаляйте прежнее приложение только для обхода ошибки подписи. Сохраните данные и <a href="https://github.com/Umichata/tokenlogue/issues" title="обратитесь за помощью">обратитесь за помощью&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Укажите имя пакета, версию Android и существенную ошибку. Перед отправкой уберите API-ключи, личную переписку и персональные пути.

<a id="ru-first-launch"></a>

<a id="-подключение-и-первый-чат"></a>
<a id="подключение-и-первый-чат"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Первый запуск

<img src="assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="assets/screenshots/android-start-ru.png" alt="Первый запуск на Android" width="320"><br>
<img src="assets/ui/frame-bottom.svg" width="320" alt="">

Первый запуск на Android.

Выберите язык, введите API-ключ OpenRouter и нажмите `Проверить ключ`. Выберите и повторите четырёхзначный PIN приложения, затем сохраните его. Через `+` выберите бесплатный или платный режим, модель и лимиты. Работа с чатами, черновиками и расходами описана в <a href="user-guide.ru.md#russian" title="руководстве пользователя">руководстве пользователя&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Верхняя левая кнопка открывает панель чатов. Для закрытия выберите чат, нажмите вне панели или используйте Back. Клавиатура может уменьшить место для действий в шапке. Закройте её, чтобы снова показать кнопки переименования и удаления.

<a id="-защита-локального-профиля"></a>
<a id="защита-локального-профиля"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Доступ и данные

Уход Tokenlogue в фон закрывает доступ. При возвращении введите PIN приложения. Сохранённый черновик восстановится. Разблокировка Android не открывает Tokenlogue автоматически.

На поддерживаемом Android 11 и новее `Забыли PIN?` запрашивает новое системное подтверждение перед сохранением нового PIN приложения. Отмена сохраняет прежний PIN и переписку. Подробнее в разделе <a href="security.ru.md#ru-recovery" title="о восстановлении и шифровании">о восстановлении и шифровании&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Резервное копирование приложения в Android отключено. Приложение использует интернет и системные возможности аутентификации. Доступ к микрофону не запрашивается. Изменение защиты устройства, удаление приложения и очистка данных могут повлиять на ключи, нужные для чтения защищённой переписки. Одна копия базы не является переносимой резервной копией.

<p align="left"><a href="user-guide.ru.md#russian"><img src="assets/ui/buttons/ru-e485e94805d4.svg" alt="Руководство пользователя" width="229" height="28"></a> <a href="security.ru.md#russian"><img src="assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a> <a href="source-materials.ru.md#russian"><img src="assets/ui/buttons/ru-324cbf015392.svg" alt="Исходные материалы" width="190" height="28"></a> <a href="../README.ru.md#russian"><img src="assets/ui/buttons/ru-b038324b5bbd.svg" alt="Tokenlogue" width="109" height="28"></a></p>
