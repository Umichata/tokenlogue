<p align="left">
<a href="android.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="android.md" title="English"><img align="right" src="assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Tokenlogue для Android

<a id="russian"></a>
<a id="lang-ru"></a>

Tokenlogue позволяет общаться с моделями OpenRouter на телефоне или планшете Android ARM64. Есть русский и английский интерфейс, отдельные черновики чатов и компоновка, которая учитывает доступное место.

<p align="left"><a href="#ru-requirements"><img src="assets/ui/buttons/ru-c8c1bdfd645d.svg" alt="Требования" width="114" height="28"></a> <a href="#ru-install"><img src="assets/ui/buttons/ru-e282b6fdb500.svg" alt="Установка" width="103" height="28"></a> <a href="#ru-update"><img src="assets/ui/buttons/ru-fee57eb0b9e5.svg" alt="Обновление" width="117" height="28"></a> <a href="#ru-first-launch"><img src="assets/ui/buttons/ru-50fa519ff78f.svg" alt="Первый запуск" width="138" height="28"></a> <a href="security.ru.md#russian"><img src="assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a></p>

<a id="ru-requirements"></a>

<a id="-требования-и-совместимость"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Требования и совместимость

- Android 7.0 или новее, API 24 и выше.
- Устройство ARM64 с поддержкой ABI `arm64-v8a`.
- API-ключ OpenRouter и интернет для проверки ключа, моделей и сообщений.
- Поддерживаемая блокировка устройства для необязательного системного восстановления PIN в Android 11 и новее.

Минимальный API не означает проверку каждой версии Android или каждого устройства. Результаты статических проверок выравнивания ELF и ZIP указаны в происхождении пакета. Статическое выравнивание 16 КиБ не подтверждает совместимость во время работы. Запуск на настоящем ARM64-устройстве с ядром 16 КиБ ещё не проверен.

<a id="ru-install"></a>

<a id="-получение-и-установка-apk"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Получение и установка APK

На странице <a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9" title="Releases">Releases&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> доступна предварительная версия Tokenlogue 0.1.0. Скачайте [APK](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) и [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS).

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Текущая версия Android | Значение |
| --- | --- |
| APK | [`Tokenlogue-0.1.0-android-arm64-v8a-v43.apk`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) |
| Версия | `0.1.0`, versionCode `43` |
| SHA-256 | `1e3ec65aaf1863eb50257aa4c090ca5fdf0b6b2c637c415d5b02056a2cf941f5` |
| SHA-256 сертификата подписи | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Перед установкой сверьте только выбранный APK с `SHA256SUMS`. Сохраните оба файла в одной папке. На компьютере используйте Bash и средства SHA-256, чтобы выполнить из этой папки следующую команду.
```bash
set -o pipefail
file='Tokenlogue-0.1.0-android-arm64-v8a-v43.apk'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Выбранный APK должен получить `OK`. Отсутствующая или повторная запись в манифесте, изменённый или отсутствующий файл вызывают ошибку команды. Контрольная сумма обнаруживает изменение байтов и не заменяет подпись издателя.

Архивы исходников и средства сборки скачиваются отдельно. Для установки и запуска Tokenlogue они не нужны.

Передайте проверенный APK на устройство, откройте его и следуйте установщику Android. Система может попросить разрешить установку из использованного файлового менеджера или браузера. Давайте разрешение только для пакета, которому доверяете. После установки его можно отключить.

<a id="ru-update"></a>

<a id="-обновление-совместимой-установки"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Обновление совместимой установки

Установите новый APK поверх совместимой прежней версии с тем же идентификатором приложения и сертификатом подписи. Сохраните данные приложения. Предварительные сборки сохраняют отображаемую версию `0.1.0`. Сборка 43 обновляет прежнюю сборку 42 благодаря большему versionCode, хотя прежний пакет показывал `0.2.0`. Удаление приложения и очистка данных не являются обычным шагом обновления и могут сделать зашифрованную переписку невосстановимой.

Если Android отказывает в обновлении, проверьте версию, архитектуру и подпись пакета. Не удаляйте прежнее приложение только для обхода ошибки подписи. Сохраните данные и <a href="https://github.com/Umichata/tokenlogue/issues" title="обратитесь за помощью">обратитесь за помощью&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Укажите имя пакета, версию Android и существенную ошибку. Перед отправкой уберите API-ключи, личную переписку и персональные пути.

<a id="ru-first-launch"></a>

<a id="-подключение-и-первый-чат"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Подключение и первый чат

<img src="assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="assets/screenshots/android-start-ru.png" alt="Первый запуск на Android" width="320"><br>
<img src="assets/ui/frame-bottom.svg" width="320" alt="">

Первый запуск на Android.

Выберите язык, введите API-ключ OpenRouter и нажмите `Проверить ключ`. Выберите и повторите четырёхзначный PIN приложения, затем сохраните его. Через `+` выберите бесплатный или платный режим, модель и лимиты. Работа с чатами, черновиками и расходами описана в <a href="user-guide.ru.md#russian" title="руководстве пользователя">руководстве пользователя&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Верхняя левая кнопка открывает панель чатов. Для закрытия выберите чат, нажмите вне панели или используйте Back. Клавиатура может уменьшить место для действий в шапке. Закройте её, чтобы снова показать кнопки переименования и удаления.

<img src="assets/ui/frame-top.svg" width="360" alt=""><br>
<img src="assets/screenshots/android-chat-ru.png" alt="Рабочее пространство чата Android" width="360"><br>
<img src="assets/ui/frame-bottom.svg" width="360" alt="">

Рабочее пространство чата Android.

<a id="-защита-локального-профиля"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Защита локального профиля

Уход Tokenlogue в фон закрывает доступ. При возвращении введите PIN приложения. Сохранённый черновик восстановится. Разблокировка Android не открывает Tokenlogue автоматически.

На поддерживаемом Android 11 и новее `Забыли PIN?` запрашивает новое системное подтверждение перед сохранением нового PIN приложения. Отмена сохраняет прежний PIN и переписку. Подробнее в разделе <a href="security.ru.md#ru-recovery" title="о восстановлении и шифровании">о восстановлении и шифровании&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Резервное копирование приложения в Android отключено. Приложение использует интернет и системные возможности аутентификации. Доступ к микрофону не запрашивается. Изменение защиты устройства, удаление приложения и очистка данных могут повлиять на ключи, нужные для чтения защищённой переписки. Одна копия базы не является переносимой резервной копией.

<p align="left"><a href="user-guide.ru.md#russian"><img src="assets/ui/buttons/ru-e485e94805d4.svg" alt="Руководство пользователя" width="229" height="28"></a> <a href="security.ru.md#russian"><img src="assets/ui/buttons/ru-287972bc31ba.svg" alt="Защита" width="83" height="28"></a> <a href="source-materials.ru.md#russian"><img src="assets/ui/buttons/ru-324cbf015392.svg" alt="Исходные материалы" width="190" height="28"></a> <a href="../README.ru.md#russian"><img src="assets/ui/buttons/ru-b038324b5bbd.svg" alt="Tokenlogue" width="109" height="28"></a></p>
