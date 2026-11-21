<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="README.ru.md#russian" title="RU"><img align="right" src="../../../docs/assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="README.md#english" title="EN"><img align="right" src="../../../docs/assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="../../../README.ru.md" title="Главная"><img src="../../../docs/assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="../../../docs/assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="../../../docs/assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="../../../docs/assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="../../../docs/assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="../../../docs/assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="../../../docs/README.ru.md" title="Карта документации"><img src="../../../docs/assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="../../../docs/user-guide.ru.md" title="Руководство"><img src="../../../docs/assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="../../../docs/providers.ru.md" title="Провайдеры"><img src="../../../docs/assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="../../../docs/analytics.ru.md" title="Статистика"><img src="../../../docs/assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="пакеты-linux"></a>

# Пакеты Linux


<a id="выбор-пакета"></a>

## <img src="../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Выбор пакета

[Руководство Linux](../../../docs/linux-appimage.ru.md) описывает AppImage 0.1.0 и опубликованный настольный пакет 0.1.1+56. Для готового приложения не нужны Python, Flutter и Java.

AppImage не подписана. Сверьте её сумму, разрешите исполнение и закройте старые копии перед запуском замены. Обычное монтирование требует FUSE. Есть вариант extract-and-run. Настольный bundle хранит исполняемый файл, библиотеки и данные вместе и не использует FUSE.

<a id="требования-рабочего-стола"></a>

## <img src="../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Требования рабочего стола

Для настольного пакета нужны Linux x86_64, совместимые системные библиотеки, GTK3, видеодрайверы дистрибутива и пользовательская сессия D-Bus. Базовая среда сборки и проверок совместимости библиотек соответствует Ubuntu 22.04. Это не означает испытание на каждом дистрибутиве.

Опубликованная AppImage 0.1.0 требует процессор x86-64-v2. Минимальный набор инструкций процессора для пакета 0.1.1 пока не установлен проверкой запуска.

Защищённые ключи хранит Secret Service, например GNOME Keyring. AppImage содержит приложение и не является резервной копией переписки. Перед переносом профиля и изменением хранилища прочитайте о [защите и восстановлении](../../../docs/security.ru.md).

<a id="исходники-и-лицензии"></a>

## <img src="../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники и лицензии

[Уведомления](notices.ru.md), [стартовый runtime AppImage](runtime/README.ru.md) и [исходные материалы](../../../docs/source-materials.ru.md) описывают разные части поставки. Новая AppImage собирается штатным producer с проверками исходников, ABI и уведомлений. Получение обычного настольного bundle — отдельный процесс.
