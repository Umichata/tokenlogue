<p align="left">
<a href="14b87ac-source-materials.ru.md" title="Русский"><img align="right" src="../assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="14b87ac-source-materials.md" title="English"><img align="right" src="../assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../../README.ru.md" title="Главная"><img src="../assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a>&nbsp;<a href="../README.ru.md" title="Документы"><img src="../assets/ui/buttons/ru-2ceca5a8917e.svg" alt="Документы" width="111" height="28"></a>
</p>

# Исторический комплект исходников

<a id="russian"></a>
<a id="lang-ru"></a>

Комплект собран 10 сентября 2026 года для <a href="v0.1.0-linux-preview.1.ru.md#russian" title="прежней Linux-сборки">прежней Linux-сборки&nbsp;<img src="../assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Он сохраняет исходные материалы той версии. Его копия также включена в более поздний [опубликованный базовый набор](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad), откуда можно повторно использовать выбранные неизменившиеся зависимости.

## 🗂️ Данные архива

<img src="../assets/ui/frame-top.svg" width="100%" alt="">

| Данные архива | Значение |
| --- | --- |
| Файл | `Tokenlogue-14b87ac-source-materials.zip` |
| Размер | 440 966 310 байт |
| SHA-256 | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| Исходники приложения | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| SHA-256 соответствующего AppImage | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

<img src="../assets/ui/frame-bottom.svg" width="100%" alt="">

Бинарное приложение в архив не входит. Отдельной ссылки на скачивание ZIP здесь нет. Чтобы получить сохранённую копию, используйте <a href="../source-materials.ru.md#russian" title="инструкцию восстановления базового набора">инструкцию восстановления базового набора&nbsp;<img src="../assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

## 🔍 Состав и целостность

ZIP содержит исходники Tokenlogue, исходные пакеты Ubuntu и правила упаковки, CPython 3.12.14, рецепты Python Build Standalone, исходные дистрибутивы Python-пакетов, пакеты Dart, Flet 0.86.5, Flutter 3.44.8, Dart bridge 1.9.0, исходные файлы шрифтов и материалы прежнего runtime.

Записанная ревизия Flutter engine равна `0cd610717bde95fd88343c64f81c11ba4e5c0010`. Файл `source-materials.json` содержит размеры и SHA-256. Файл `coverage.json` связывает материалы с компонентами.

Распакуйте ZIP, откройте терминал в папке `Tokenlogue-14b87ac-source-materials` и запустите включённый проверяющий скрипт с Python 3.
```bash
python3 verify_materials.py
```

Скрипт проверяет соответствие предоставленных файлов манифесту. Он не подтверждает наличие каждого файла, необходимого для полной пересборки.

## 📌 Границы исторического комплекта

Для прежних исходников Ubuntu libgcrypt20 сохранена [публикация Launchpad](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640). [Историческая ревизия type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c) указывает на прежний исходный код. В ZIP есть рецепты Alpine, которые могут соответствовать старому runtime, но нет подтверждённой описи пакетов его сборки.

Опись зависимостей Flutter engine содержит 109 записей. Часть внешних входов Git и CIPD не включена. Сборка engine без сети, начальная сборка компилятора, перелинковка, создание подмножеств шрифтов и пересборка всего приложения только из этого ZIP не подтверждены.

У более поздних пакетов другие исходники приложения, входы runtime и некоторые версии зависимостей. Например, следующий базовый набор заменяет Dart `archive` 4.2.0 на 4.3.0, Dart `image` 4.9.2 на 4.10.1, `flutter_secure_storage_linux` 3.0.2 на 3.0.3 и Ubuntu `libgcrypt20` 1.9.4-3ubuntu3.2 на 1.9.4-3ubuntu3.3. Исторический ZIP сохраняет первоначальные версии.

Чтобы выбрать соответствующие файлы, используйте <a href="../source-materials.ru.md#russian" title="руководство по исходным материалам">руководство по исходным материалам&nbsp;<img src="../assets/ui/inline-link.svg" alt="" width="17" height="17"></a> и индекс из вашего пакета.
