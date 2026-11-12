<p align="left">
<a href="linux-appimage.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="linux-appimage.md" title="English"><img align="right" src="assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Tokenlogue для Linux

<a id="russian"></a>
<a id="lang-ru"></a>

<a id="ru-preview-status"></a>
> **Начальная предварительная версия 0.1.0 — черновик.** Пока выпуск находится в черновике, пакеты приложения и их исходные архивы недоступны для публичного скачивания. Имена файлов и суммы ниже описывают подготовленный комплект.

Запускайте Tokenlogue на рабочем столе Linux в формате AppImage. Для обычного использования не нужно отдельно устанавливать Python, Flutter или инструменты сборки. В текущей предварительной версии есть русский и английский интерфейс.

<img src="assets/ui/frame-top.svg" width="880" alt=""><br>
<img src="assets/screenshots/linux-chat.png" alt="Иллюстрация рабочего пространства чата Linux" width="880"><br>
<img src="assets/ui/frame-bottom.svg" width="880" alt="">

Иллюстрация рабочего пространства Linux с демонстрационными данными на английском языке. Точный набор элементов зависит от выбранного чата и доступного места.

<p align="left"><a href="#ru-requirements"><img src="assets/ui/buttons/ru-c8c1bdfd645d.svg" alt="Требования" width="114" height="28"></a> <a href="#ru-download"><img src="assets/ui/buttons/ru-a51ebf3766a4.svg" alt="Скачивание" width="115" height="28"></a> <a href="#ru-run"><img src="assets/ui/buttons/ru-dbadd61442d5.svg" alt="Запуск" width="77" height="28"></a> <a href="#ru-updates"><img src="assets/ui/buttons/ru-fee57eb0b9e5.svg" alt="Обновление" width="117" height="28"></a> <a href="#ru-help"><img src="assets/ui/buttons/ru-9079b2556a7e.svg" alt="Помощь" width="87" height="28"></a></p>

<a id="ru-requirements"></a>

<a id="-требования"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Требования

- Linux x86_64 и процессор с поддержкой x86-64-v2. Базовая среда системных библиотек — Ubuntu 22.04.
- Графический рабочий стол, GTK3 и его зависимости. Одного GTK4 недостаточно.
- Работающие графические драйверы вашего дистрибутива.
- Пользовательская сессия D-Bus и доступный разблокированный Secret Service, например GNOME Keyring. Включённый клиент libsecret сам по себе не является хранилищем ключей.
- FUSE для обычного запуска или место во временном каталоге для extract-and-run.
- API-ключ OpenRouter и интернет для проверки ключа, загрузки моделей и отправки сообщений.

Защита при блокировке экрана и сне рассчитана на поддерживаемую сессию Cinnamon/X11. В других окружениях и Wayland автоматическое наблюдение может быть ограничено. Проверяйте панель защиты приложения и при необходимости блокируйте его вручную.

<a id="ru-download"></a>

<a id="-скачивание-и-проверка"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Скачивание и проверка

В <a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9" title="Черновик выпуска">черновике выпуска&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> подготовлены [AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) Tokenlogue 0.1.0 и [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS). Ссылки на файлы черновика доступны сопровождающим репозитория для проверки. Публичными они станут только после публикации выпуска.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Подготовленный файл | Значение |
| --- | --- |
| AppImage | [`Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) |
| SHA-256 | `247497d8f97aae0c16cab282edc1c6cbf47747c7b3597e3ba23b388558e40646` |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Сохраните AppImage и `SHA256SUMS` в одной папке. Используйте Bash и средства SHA-256, чтобы проверить из этой папки только выбранный пакет.
```bash
set -o pipefail
file='Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Выбранная AppImage должна получить `OK`. Отсутствующая или повторная запись в манифесте, изменённый или отсутствующий файл вызывают ошибку команды. Сумма обнаруживает изменение байтов, но не заменяет подпись издателя. Эта AppImage не подписана. Не подменяйте ожидаемую сумму хешем файла, который не прошёл проверку.

Архивы исходников и средства сборки скачиваются отдельно. Для установки и запуска Tokenlogue они не нужны.


<a id="ru-run"></a>

<a id="-запуск-tokenlogue"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Запуск Tokenlogue

Один раз разрешите исполнение и запустите проверенную AppImage от своего обычного пользователя.
```bash
chmod u+x ./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
```

Хранить файл можно в удобной папке. После выдачи прав его можно открыть через файловый менеджер, поддерживающий запуск программ. AppImage не добавляет пункт меню автоматически. Не запускайте её через `sudo` или `pkexec`.

<a id="ru-without-fuse"></a>

<a id="-запуск-без-fuse"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Запуск без FUSE

Если система не может монтировать AppImage через FUSE, используйте extract-and-run.
```bash
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage --appimage-extract-and-run
```

Программа распакует файлы во временный каталог и запустится без FUSE. Убедитесь, что во временной файловой системе хватает места для распакованных файлов.

<a id="ru-updates"></a>

<a id="-обновление-с-сохранением-профиля"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Обновление с сохранением профиля

Перед запуском замены закройте все прежние копии Tokenlogue. Проверьте новый файл и запустите его в той же учётной записи ОС. Автоматического обновления нет. Замена AppImage не удаляет отдельно сохранённые данные приложения.

Если локальный профиль содержит незащищённые поля переписки, первый успешный вход защищает их до открытия чатов. Во время работы с профилем держите другие экземпляры приложения закрытыми. Не открывайте защищённый профиль несовместимым ПО и не меняйте его базу без совместимой резервной копии.

Одна база не является полной переносимой резервной копией. Ключ шифрования остаётся в системном хранилище. Его потеря может сделать переписку невосстановимой. Перед переносом данных или изменением связки ключей прочитайте <a href="security.ru.md#ru-encryption" title="о защите переписки">о защите переписки&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

<a id="ru-current-protection"></a>
<a id="ru-system-recovery"></a>

<a id="-необязательное-восстановление-через-учётную-запись-linux"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Необязательное восстановление через учётную запись Linux

Основной способ восстановления PIN в Linux — заранее сохранённый <a href="security.ru.md#ru-recovery" title="резервный код">резервный код&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Для него не нужна настройка администратора. Дополнительный пункт `Системное восстановление Linux` требует policy Tokenlogue для polkit и системного агента аутентификации.

Если вы выбираете этот способ, изучите [policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) и [помощник установки](../packaging/linux/polkit/tokenlogue-polkit.py) из исходного комплекта, соответствующего приложению. Однократная команда установки приведена ниже. Выполняйте её из корня репозитория. Она устанавливает policy, а не приложение.
```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
```

Проверьте установленную policy от обычного пользователя.
```bash
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

Помощник устанавливает только проверенную policy Tokenlogue. Он отказывается заменять неожиданные файлы и не меняет пароли Linux, PAM или настройки входа. Сам Tokenlogue по-прежнему запускается обычным пользователем. Каждая попытка восстановления требует нового подтверждения вашей учётной записи в системном окне. Вводите пароль Linux только там.

Для удаления только этой policy используйте команду ниже. Данные приложения сохранятся.
```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a id="ru-help"></a>

<a id="-помощь-при-запуске"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Помощь при запуске

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Проблема | Что проверить |
| --- | --- |
| Отказано в доступе | Право исполнения и возможность запуска программ на выбранной файловой системе. |
| Ошибка монтирования FUSE | Попробуйте extract-and-run выше. |
| Не найдена библиотека GTK | Восстановите GTK3 и его зависимости через пакетный менеджер дистрибутива. |
| Хранилище ключей недоступно | Разблокируйте Secret Service и проверьте пользовательскую сессию D-Bus. Сохраните файлы профиля. |
| Illegal instruction | Убедитесь, что процессор поддерживает x86-64-v2. |
| Ошибка графики | Проверьте драйверы системы и GTK3. Сообщение в терминале может объяснить причину. |
| Уже работает другая копия | Закройте другую копию с тем же каталогом данных. Не обходите блокировку профиля. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

В <a href="https://github.com/Umichata/tokenlogue/issues" title="обращении за помощью">обращении за помощью&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> укажите имя пакета, дистрибутив, рабочее окружение и существенную ошибку. Перед отправкой уберите API-ключи, личную переписку и персональные пути.

<a id="ru-delete"></a>

<p align="left"><a href="user-guide.ru.md#russian"><img src="assets/ui/buttons/ru-3761fd15c208.svg" alt="Подключение и работа с чатами" width="272" height="28"></a> <a href="security.ru.md#russian"><img src="assets/ui/buttons/ru-16ff70bb711a.svg" alt="PIN, восстановление и удаление профиля" width="343" height="28"></a></p>

<p align="left"><a href="source-materials.ru.md#russian"><img src="assets/ui/buttons/ru-da69704e7a6e.svg" alt="Исходники и лицензии" width="198" height="28"></a> <a href="../README.ru.md#russian"><img src="assets/ui/buttons/ru-b038324b5bbd.svg" alt="Tokenlogue" width="109" height="28"></a></p>
