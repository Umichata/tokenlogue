<p align="center">
  <img src="docs/assets/tokenlogue-logo-transparent.png" alt="Tokenlogue" width="104">
</p>

# Tokenlogue

[English](#english) · [Русский](#russian)

[Home / Главная](https://github.com/Umichata/tokenlogue/tree/main) · [**Android**](https://github.com/Umichata/tokenlogue/tree/android) · [Linux](https://github.com/Umichata/tokenlogue/tree/linux)

<a id="english"></a>
<a id="lang-en"></a>

## English

Use OpenRouter models from your Android phone or tablet. Tokenlogue keeps your chats, drafts and model choices in one mobile workspace.

[Install](#en-install) · [First chat](#en-chat) · [Protection](docs/security.md#english)

<a href="docs/assets/screenshots/android-chat-en.png"><img src="docs/assets/screenshots/android-chat-en.png" alt="Tokenlogue chat on an Android tablet" width="320"></a>

Tokenlogue chat on an Android tablet.

<a id="en-install"></a>
### Install or update

You need **ARM64 Android 7.0 / API 24 or later**. This minimum does not mean every Android version has been tested. Static 16 KiB checks passed, while operation on a native ARM64 device with a 16 KiB kernel has not yet been checked.

For this preview, choose `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk` and `RELEASE_SHA256SUMS` from [Releases](https://github.com/Umichata/tokenlogue/releases). If this preview is not listed, its downloads are not public yet. Check only the APK against its manifest entry as explained in the Android guide below. You do not need a separate Python or Flutter installation or the source archives to run Tokenlogue.

Allow installation from your chosen file manager or browser, open the verified APK and follow Android's prompts. For an update, install over a compatible previous version with the same signing certificate. Do not uninstall or clear application data as a routine update step.

[Full Android installation guide](docs/android.md#english)

<a id="en-chat"></a>
### Start a conversation

Add your own OpenRouter key, complete its online check and set a PIN. Create a chat and select a model. The draft and model choice remain with that conversation. Open the chat actions to rename or delete it.

A chat budget, the key's OpenRouter limit and the account balance are separate. Token and cost estimates are approximate. Turning off paid-request confirmation applies from the first request in that chat, while limits remain active.

[Chat guide](docs/user-guide.md#english) · [PIN, encryption and Android recovery](docs/security.md#english)

### Know what is protected

Selected local conversation fields are encrypted, not the whole device. System recovery needs a supported and configured Android screen lock and access to the original protected encryption key. Deleting the local profile is irreversible and does not refund or delete your OpenRouter account.

[Sources and provenance limits](docs/source-materials.md#english) · [Third-party licenses](THIRD_PARTY_NOTICES.md#english) · [MIT license](LICENSE)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Общайтесь с моделями OpenRouter на телефоне или планшете Android. Tokenlogue объединяет чаты, черновики и выбор модели в одном мобильном рабочем пространстве.

[Установка](#ru-install) · [Первый чат](#ru-chat) · [Защита](docs/security.md#russian)

<a href="docs/assets/screenshots/android-chat-ru.png"><img src="docs/assets/screenshots/android-chat-ru.png" alt="Рабочий чат Tokenlogue на планшете Android" width="320"></a>

Рабочий чат Tokenlogue на планшете Android.

<a id="ru-install"></a>
### Установка и обновление

Нужен **Android 7.0 / API 24 или новее с ARM64**. Поддерживаемый минимум не означает проверку каждой версии Android. Статические проверки 16 КиБ пройдены, но работа на нативном ARM64-устройстве с ядром 16 КиБ пока не проверена.

Для этой предварительной версии выберите `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk` и `RELEASE_SHA256SUMS` на странице [Releases](https://github.com/Umichata/tokenlogue/releases). Если этой версии нет в списке, её загрузки ещё не опубликованы. Проверьте только APK по его записи в манифесте, как описано в руководстве Android ниже. Для запуска Tokenlogue не нужны отдельная установка Python или Flutter и архивы исходников.

Разрешите установку выбранному файловому менеджеру или браузеру, откройте проверенный APK и следуйте подсказкам Android. Для обновления устанавливайте его поверх совместимой прежней версии с тем же сертификатом. Не удаляйте приложение и не очищайте данные как обычный шаг обновления.

[Подробная установка Android](docs/android.md#russian)

<a id="ru-chat"></a>
### Начало переписки

Добавьте собственный ключ OpenRouter, дождитесь его проверки через сеть и задайте PIN. Создайте чат и выберите модель. Черновик и выбор модели сохраняются для этого разговора. Действия чата позволяют переименовать или удалить его.

Бюджет чата, лимит ключа OpenRouter и баланс аккаунта различаются. Оценка токенов и стоимости приблизительна. Отключение подтверждения платного запроса действует с первого запроса выбранного чата, а лимиты продолжают работать.

[Руководство по чатам](docs/user-guide.md#russian) · [PIN, шифрование и восстановление Android](docs/security.md#russian)

### Что защищено

Шифруются отдельные локальные поля переписки, а не всё устройство. Для системного восстановления нужны поддерживаемая и настроенная блокировка Android и доступ к исходному защищённому ключу шифрования. Удаление локального профиля необратимо и не возвращает средства и не удаляет аккаунт OpenRouter.

[Исходники и ограничения происхождения](docs/source-materials.md#russian) · [Сторонние лицензии](THIRD_PARTY_NOTICES.md#russian) · [Лицензия MIT](LICENSE)
