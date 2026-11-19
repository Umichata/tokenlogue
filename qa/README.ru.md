[English](README.md) · [Русский](README.ru.md)

# Проверки на Android

Используйте эмулятор Android с одноразовым профилем. Задайте `FLUTTER_ROOT`, `ANDROID_HOME` и `JAVA_HOME` по [руководству сборки](../apps/android_dart/README.ru.md). В `QA_DEVICE` укажите серийный идентификатор этого эмулятора.

```bash
qa/android_dart_integration/run "$QA_DEVICE"
```

Сценарий готовит приложение во временном каталоге и запускает интеграционный тест Flutter в `io.github.umichata.tokenlogue.dart.qa`. В начальную форму вводится искусственное значение. Тест проверяет местное определение сервиса без запроса к провайдеру.

Для независимого измерения установленного release APK соберите внешний пакет Android instrumentation. Понадобятся Android SDK, JDK 17, OpenSSL и zip. Установите его на тот же тестовый эмулятор, что и release APK.

```bash
mkdir -p out
qa/android_ui/build "$PWD/out/tokenlogue-ui-qa.apk"
adb -s "$QA_DEVICE" install out/tokenlogue-ui-qa.apk
adb -s "$QA_DEVICE" shell am instrument -w \
  -e package io.github.umichata.tokenlogue.dart -e measure size \
  io.github.umichata.tokenlogue.qa/.PublicWindowProbe
```

Размер установленного приложения сообщает Android. Для активного экрана инструмент также может показать наличие известных публичных элементов управления. Для обычного системного восстановления требуется подтверждение личности в окне Android. Вводите свои данные только в предназначенное для них поле приложения или системы.
