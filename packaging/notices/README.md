[English](README.md#english) · [Русский](README.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Libraries and fonts

[Home](../../README.md) · [Documentation](../../docs/README.md)

Tokenlogue supplies original third-party notices alongside the software they describe. Android and Linux include the notices relevant to each package.

<a id="-read-the-original-texts"></a>
## License texts

- [libffi 3.4.4](inputs/libffi-3.4.4-LICENSE.txt) belongs to the Android Python runtime.
- [CFFI’s libffi 3.4.4](inputs/libffi-cffi-3.4.4-LICENSE.txt) is statically included in the project’s source-built Android and Linux CFFI wheels.
- [Dart bridge 1.10.0](inputs/dart-bridge-1.10.0-LICENSE.txt) connects the Android Python runtime and Dart.
- KaTeX includes the [MIT license](inputs/flutter_math_fork-0.7.4-katex-LICENSE.txt), [font copyright](inputs/KaTeX-COPYRIGHT.txt) and [SIL Open Font License 1.1](inputs/SIL-OFL-1.1.txt).
- Material Icons includes its [original declaration](inputs/MaterialIcons_LICENSE.txt) and [Google copyright notice](inputs/MaterialIcons-COPYRIGHT.txt).

- tzdata includes its [Apache 2.0 license](inputs/tzdata-2026.6-LICENSE-APACHE.txt) and [IANA public-domain notice](inputs/tzdata-2026.6-LICENSE.txt).

Legal texts remain complete and unchanged in their original language. The accompanying manifest maps them to exact components and sources. Android uses a subset of Material Icons produced by Flutter. The Linux font matches the original input. These transformations are described separately from the legal texts.

The runtime libffi notice does not identify the library inside the separate CFFI wheel. The source-built CFFI packages have their own source, patches and binding to the included libffi. See [source materials](../../docs/source-materials.md#english).
