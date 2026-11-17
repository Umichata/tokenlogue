[English](#english) · [Русский](#russian)

<a id="english"></a>

# Native dependency sources

These inputs supply CFFI and PyCryptodomex for Linux and Android, and msgpack for Android. The application uses the same component versions as before. The wheels are compiled from the exact source archives identified in `wheels.lock.json`. They are dependency inputs to the existing application packaging helpers.

CFFI contains a static build of libffi 3.4.4. Its original license and a separate build declaration are included inside each CFFI wheel under `licenses/libffi`. This libffi belongs to CFFI. The Python runtime has its own independently identified libffi.

The Linux wheels are compiled inside the Ubuntu 22.04 baseline using GCC 11. Android uses CPython 3.12.14, API 24 and NDK 28.2.13676358. Android libffi includes the two retained CPython Android patches. The CFFI patches select the supplied static library. Android PyCryptodomex retains the existing mobile loader patch. Original licenses and source archives are unchanged.

## Verify the supplied inputs

From the project directory, run the verifier for the intended platform.

```bash
python3 packaging/native_wheels/verify.py inputs --root . --platform android
python3 packaging/native_wheels/verify.py inputs --root . --platform linux
```

The verifier checks archive checksums, wheel records, component identity, native members and original notices. The existing Android and Linux helpers also compare the packaged native payloads with these inputs. Android's recorded NDK strip transformation is checked separately from the original compiled bytes.

## Rebuild dependency wheels

Use an isolated CPython 3.12.14 environment and uv 0.12.8. The original Python build-tool wheels are retained under `sources/build-tools`. Install the locked tools without consulting an index. Install crossenv from its retained exact source archive when building Android.

```bash
uv venv --python 3.12.14 /tmp/tokenlogue-native-tools
uv pip sync --python /tmp/tokenlogue-native-tools/bin/python \
  --no-index --find-links packaging/native_wheels/sources/build-tools \
  --require-hashes packaging/native_wheels/build-requirements.txt
uv pip install --python /tmp/tokenlogue-native-tools/bin/python \
  --no-deps --no-build-isolation \
  packaging/native_wheels/sources/crossenv-e5e615651f794d060d9484eab463861fef2a2019.tar.gz
```

For Android, obtain the exact support archive identified by URL, size and SHA-256 in `wheels.lock.json`. This archive supplies target Python headers and configuration. The recipe verifies it before extraction. Use the already installed NDK of the stated version.

```bash
/tmp/tokenlogue-native-tools/bin/python packaging/native_wheels/build.py \
  --platform android --work-dir /tmp/tokenlogue-native-android \
  --output /tmp/tokenlogue-native-android-result \
  --support-archive python-android-mobile-forge-3.12.14.tar.gz \
  --ndk "${ANDROID_SDK_ROOT}/ndk/28.2.13676358"
```

For Linux, run the following command inside the project's Ubuntu 22.04 build environment with the same locked Python tools. A newer host libc is rejected to prevent raising the package's ABI requirements.

```bash
/tmp/tokenlogue-native-tools/bin/python packaging/native_wheels/build.py \
  --platform linux --work-dir /tmp/tokenlogue-native-linux \
  --output /tmp/tokenlogue-native-linux-result
```

Work and output directories must be new. Compilation uses physical paths under `/tmp` or `/var/tmp` and compiler path mappings. The recipe does not modify an application package or signing material. Rebuilt wheels require their own input and final-package checks before use. These instructions do not promise byte-for-byte reproducibility of every third-party tool.

<a id="russian"></a>

# Исходники нативных зависимостей

Эти материалы содержат CFFI и PyCryptodomex для Linux и Android, а также msgpack для Android. Версии компонентов приложения сохранены. Wheels компилируются из точных исходных архивов, перечисленных в `wheels.lock.json`. Они используются как зависимости существующими сценариями упаковки приложения.

В CFFI статически включена libffi 3.4.4. Её оригинальная лицензия и отдельное описание сборки находятся внутри каждого CFFI wheel в `licenses/libffi`. Эта libffi относится к CFFI. В составе Python runtime находится отдельная libffi с собственными сведениями о происхождении.

Linux wheels компилируются в базовой среде Ubuntu 22.04 с GCC 11. Android использует CPython 3.12.14, API 24 и NDK 28.2.13676358. Android libffi включает два сохранённых патча CPython Android. Патчи CFFI выбирают предоставленную статическую библиотеку. Android PyCryptodomex сохраняет действующий патч мобильного загрузчика. Оригинальные лицензии и исходные архивы не изменены.

## Проверить готовые входы

В каталоге проекта запустите проверку нужной платформы.

```bash
python3 packaging/native_wheels/verify.py inputs --root . --platform android
python3 packaging/native_wheels/verify.py inputs --root . --platform linux
```

Проверяются суммы архивов, wheel records, соответствие компонентов, нативные файлы и оригинальные уведомления. Существующие сценарии Android и Linux также сравнивают упакованные нативные файлы с этими входами. Зафиксированное преобразование Android средствами NDK strip проверяется отдельно от исходных скомпилированных байтов.

## Пересобрать wheels зависимостей

Используйте отдельное окружение CPython 3.12.14 и uv 0.12.8. Оригинальные wheels инструментов Python сохранены в `sources/build-tools`. Установите закреплённые инструменты без обращения к индексу. Для Android установите crossenv из сохранённого точного исходного архива.

```bash
uv venv --python 3.12.14 /tmp/tokenlogue-native-tools
uv pip sync --python /tmp/tokenlogue-native-tools/bin/python \
  --no-index --find-links packaging/native_wheels/sources/build-tools \
  --require-hashes packaging/native_wheels/build-requirements.txt
uv pip install --python /tmp/tokenlogue-native-tools/bin/python \
  --no-deps --no-build-isolation \
  packaging/native_wheels/sources/crossenv-e5e615651f794d060d9484eab463861fef2a2019.tar.gz
```

Для Android получите точный support-архив по URL, размеру и SHA-256 из `wheels.lock.json`. Он предоставляет заголовки и конфигурацию целевого Python. Рецепт проверяет архив перед извлечением. Используйте уже установленный NDK указанной версии.

```bash
/tmp/tokenlogue-native-tools/bin/python packaging/native_wheels/build.py \
  --platform android --work-dir /tmp/tokenlogue-native-android \
  --output /tmp/tokenlogue-native-android-result \
  --support-archive python-android-mobile-forge-3.12.14.tar.gz \
  --ndk "${ANDROID_SDK_ROOT}/ndk/28.2.13676358"
```

Для Linux выполните следующую команду в среде сборки проекта на Ubuntu 22.04 с теми же закреплёнными инструментами Python. Более новая libc сборщика отклоняется, чтобы не повышать требования пакета к ABI.

```bash
/tmp/tokenlogue-native-tools/bin/python packaging/native_wheels/build.py \
  --platform linux --work-dir /tmp/tokenlogue-native-linux \
  --output /tmp/tokenlogue-native-linux-result
```

Рабочие и выходные каталоги должны быть новыми. Компиляция использует физические пути в `/tmp` или `/var/tmp` и преобразования путей компилятора. Рецепт не изменяет пакет приложения или материалы подписи. Перед использованием пересобранных wheels нужно проверить их входы и конечный пакет. Эти инструкции не обещают побайтовую воспроизводимость всех сторонних инструментов.
