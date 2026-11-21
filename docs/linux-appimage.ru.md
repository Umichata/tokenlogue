<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="linux-appimage.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="linux-appimage.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="user-guide.ru.md" title="Руководство"><img src="assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="providers.ru.md" title="Провайдеры"><img src="assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="analytics.ru.md" title="Статистика"><img src="assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="tokenlogue-для-linux"></a>

# Tokenlogue для Linux


> В **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** доступны два APK для Android ARM64 ([Python +56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) и [Dart +18](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk)) и [архив для Linux x86_64 +56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-linux-x86_64-bundle.tar.gz). Перед установкой проверьте требования платформы и контрольную сумму файла.


<a id="требования"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Требования

Нужны Linux x86_64, графический рабочий стол, glibc 2.34 или новее, libstdc++ с `GLIBCXX_3.4.29`, GTK3 и видеодрайверы дистрибутива. Базовая среда системных библиотек соответствует Ubuntu 22.04. Прежняя AppImage 0.1.0 требует процессор x86-64-v2. Работа bundle 0.1.1 на более старых процессорах не проверена. Также необходимы пользовательская сессия D-Bus и разблокированный Secret Service, например GNOME Keyring. Включённый клиент libsecret не является хранилищем ключей.

Для работы с моделями нужен ключ провайдера выбранного чата. Поддерживаемое наблюдение за блокировкой и сном рассчитано на Cinnamon/X11. В других окружениях и Wayland оно может быть ограничено. Если наблюдение недоступно, блокируйте приложение вручную.

<a id="ru-download"></a>
<a id="ru-local-bundle"></a>
<a id="настольный-bundle-011"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Настольный bundle 0.1.1

Скачайте [архив приложения для Linux x86_64](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-linux-x86_64-bundle.tar.gz) со страницы [0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1). Это архив приложения с библиотеками, а не AppImage. Он не требует FUSE и не подписан.

| Параметр | Значение |
| --- | --- |
| Файл | [`Tokenlogue-0.1.1+56-linux-x86_64-bundle.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-linux-x86_64-bundle.tar.gz) |
| Версия | 0.1.1+56 |
| Архитектура | Linux x86_64 |
| Размер | 34 974 386 байт |
| SHA-256 | `6ab4f7525ea9ec7287b6d4d3c53e95089d590e856874c9695e793186149e03d9` |
| Каталог после распаковки | `Tokenlogue-0.1.1+56-linux-x86_64/` |

Закройте прежние копии Tokenlogue. В папке с полученным архивом проверьте его сумму.

```bash
printf '%s  %s\n' \
  '6ab4f7525ea9ec7287b6d4d3c53e95089d590e856874c9695e793186149e03d9' \
  'Tokenlogue-0.1.1+56-linux-x86_64-bundle.tar.gz' | sha256sum --check -
```

После `OK` распакуйте весь комплект в новую папку и запустите его от обычного пользователя. В этом примере `tokenlogue-local` ещё не существует. Если команда сообщает об ошибке, остановитесь.

```bash
mkdir tokenlogue-local &&
tar --extract --gzip --file 'Tokenlogue-0.1.1+56-linux-x86_64-bundle.tar.gz' \
  --directory tokenlogue-local --no-same-owner &&
./tokenlogue-local/Tokenlogue-0.1.1+56-linux-x86_64/tokenlogue
```

Не переносите один исполняемый файл без соседних библиотек и данных. Используйте ту же учётную запись ОС и прежнее разблокированное защищённое хранилище. Замена каталога приложения не требует удаления профиля. См. [безопасное обновление](#безопасное-обновление).

<a id="ru-published-appimage"></a>
<a id="опубликованная-appimage"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Опубликованная AppImage

Это прежний публичный файл **0.1.0**. Версия 0.1.1 поставляется настольным bundle. Архив исходников проекта не является установленным приложением.

| Файл | Значение |
| --- | --- |
| <a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage" title="AppImage x86_64"><img src="assets/ui/buttons/v3-ru-6c1977e489d0.svg" alt="AppImage x86_64" width="155" height="30"></a> | `Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage` |
| Версия | 0.1.0+43 |
| SHA-256 | `247497d8f97aae0c16cab282edc1c6cbf47747c7b3597e3ba23b388558e40646` |
| Манифест | <a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS" title="SHA256SUMS"><img src="assets/ui/buttons/v3-ru-f1ce47c3a95b.svg" alt="SHA256SUMS" width="125" height="30"></a> |

Сохраните AppImage и манифест рядом. Проверьте только выбранный файл с помощью Bash и средств SHA-256.

```bash
set -o pipefail
file='Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Продолжайте только после `OK` для выбранной AppImage. Она не подписана. Суммы подтверждают целостность и не являются подписью издателя.

<a id="запуск-appimage"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Запуск AppImage

Разрешите исполнение и запустите проверенный файл от обычного пользователя.

```bash
chmod u+x ./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
```

Если FUSE недоступен, используйте следующий параметр. Во временном каталоге должно хватать места.

```bash
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage --appimage-extract-and-run
```

<a id="запуск-локального-настольного-bundle"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Запуск настольного комплекта

Используйте [инструкцию по установке комплекта](#ru-local-bundle) выше с точным именем, суммой и порядком распаковки. Сохраняйте весь каталог приложения. Параметры AppImage к этому формату не относятся.

<a id="безопасное-обновление"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Безопасное обновление

Закройте все старые копии перед запуском замены от той же учётной записи ОС с доступом к прежнему системному хранилищу ключей. Сверьте новый пакет. Замена файлов приложения сохраняет отдельно расположенный профиль. Автоматического обновления нет.

Первый успешный вход защищает поддерживаемые открытые поля переписки до открытия чатов. Не допускайте записи несовместимых версий в один профиль. Одна копия базы не является переносимой резервной копией, поскольку ключ шифрования хранится отдельно. См. [защиту данных](security.ru.md).

<a id="дополнительное-системное-восстановление-linux"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Дополнительное системное восстановление Linux

Основной способ восстановления PIN — заранее сохранённый [резервный код](security.ru.md#ru-linux-code). Для отдельного системного восстановления нужны policy Tokenlogue для polkit и системный агент аутентификации.

Изучите [policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) и [помощник установки](../packaging/linux/polkit/tokenlogue-polkit.py) из подходящего исходного комплекта. В каталоге исходников однократно установите policy, затем проверьте её от обычного пользователя.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

Команда устанавливает только policy. Пароли Linux, PAM и настройки входа не меняются. Вводите пароль ОС только в системном окне. Сам Tokenlogue запускается без `sudo` и `pkexec`.

Удалить только эту policy можно следующей командой. Данные приложения сохраняются.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a id="помощь-при-запуске"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Помощь при запуске

| Проблема | Действие |
| --- | --- |
| Нет права исполнения | Проверьте права файла и разрешение запуска на файловой системе. |
| Не работает FUSE | Используйте extract-and-run для AppImage. |
| Не найдена GTK | Восстановите GTK3 и зависимости средствами дистрибутива. |
| Хранилище ключей недоступно | Разблокируйте Secret Service и проверьте сессию D-Bus. Сохраните файлы профиля. |
| Illegal instruction | Проверьте требования пакета к процессору. Опубликованная AppImage требует x86-64-v2. |
| Ошибка графики | Проверьте видеодрайверы дистрибутива. |
| Профиль уже открыт | Закройте использующую его копию. Не обходите блокировку. |

[Сообщите о проблеме](https://github.com/Umichata/tokenlogue/issues), указав версию, дистрибутив и рабочую среду. Уберите личные сообщения, ключи и персональные пути.
