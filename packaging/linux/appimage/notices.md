# Licenses inside the AppImage / Лицензии внутри AppImage

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

The Linux package carries the original licenses and copyright notices for its included software. Tokenlogue's own code uses the [MIT license](../../../LICENSE).

### Find the original texts

After extracting your verified AppImage, these paths are relative to its extracted root:

| Path | What it contains |
| --- | --- |
| `LICENSE` | Tokenlogue's license |
| `THIRD_PARTY_NOTICES.md` | Component index and notice locations |
| `usr/share/doc/tokenlogue/notices.json` | Component mapping, file hashes and source references |
| `usr/share/doc/tokenlogue/licenses/` | Original third-party texts |
| `usr/share/doc/tokenlogue/licenses/supplemental/` | Additional font declaration, attribution and source mapping |

The [Linux guide](../../../docs/linux-appimage.md#english) covers checksum verification and launch options. An extraction offset belongs to a particular AppImage and should not be reused for a different download.

### Read the collection

The collection covers Python, Flutter and its plugins, native libraries, fonts and the AppImage runtime. Material Icons retains its original declaration and Google attribution. The Linux font matches the original font input. KaTeX license and font notices remain with their corresponding fonts.

Debian copyright files can mention source-package files that are absent from the AppImage. Python's upstream license collection can also describe optional modules that are not included. Use the component mapping to identify the software actually supplied. A license reference does not imply that an optional feature is available in Tokenlogue.

Original legal texts are neither translated nor shortened. Their terms take precedence over this explanation. Source archives are separate from the license collection. See [available source materials and their limitations](../../../docs/source-materials.md#english).

[Back to the Linux package](README.md#english)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Пакет Linux содержит оригинальные лицензии и уведомления об авторских правах включённого программного обеспечения. Собственный код Tokenlogue распространяется по [лицензии MIT](../../../LICENSE).

### Где найти оригинальные тексты

После распаковки проверенного AppImage пути отсчитываются от корня извлечённого каталога:

| Путь | Содержимое |
| --- | --- |
| `LICENSE` | Лицензия Tokenlogue |
| `THIRD_PARTY_NOTICES.md` | Список компонентов и расположение уведомлений |
| `usr/share/doc/tokenlogue/notices.json` | Связи компонентов, суммы файлов и сведения об источниках |
| `usr/share/doc/tokenlogue/licenses/` | Оригинальные тексты сторонних компонентов |
| `usr/share/doc/tokenlogue/licenses/supplemental/` | Дополнительная декларация шрифта, авторство и связь с источником |

В [руководстве для Linux](../../../docs/linux-appimage.md#russian) описаны проверка суммы и варианты запуска. Смещение файловой системы относится к конкретному AppImage, его нельзя переносить на другой файл.

### Как читать комплект

В комплект входят уведомления Python, Flutter и его плагинов, нативных библиотек, шрифтов и runtime AppImage. Для Material Icons сохранены исходная декларация и сведения об авторстве Google. Шрифт Linux совпадает с исходным файлом. Лицензия KaTeX и уведомления о шрифтах находятся вместе с соответствующими шрифтами.

Copyright-файлы Debian могут описывать файлы исходного пакета, отсутствующие в AppImage. Коллекция лицензий Python может упоминать необязательные модули, которые не включены. Сверяйтесь со связями компонентов, чтобы определить фактический состав. Упоминание в лицензии не означает доступность необязательной функции в Tokenlogue.

Оригинальные юридические тексты не переводятся и не сокращаются. Их условия имеют приоритет над этим пояснением. Архивы исходников поставляются отдельно от лицензий. Подробнее о [доступных исходных материалах и ограничениях](../../../docs/source-materials.md#russian).

[К пакету Linux](README.md#russian)
