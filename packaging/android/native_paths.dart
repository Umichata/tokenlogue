import 'dart:io';

import 'package:flutter/services.dart';

Future<void> configureTokenlogueNativePaths(
  Map<String, String> environment,
) async {
  if (!Platform.isAndroid) return;
  const channel = MethodChannel('io.github.umichata.tokenlogue.native_paths');
  final paths = await channel.invokeMapMethod<String, String>(
    'nativeEnvironment',
  );
  const expected = {'ANDROID_NATIVE_LIBRARY_DIR', 'ANDROID_APK_NATIVE_PREFIX'};
  if (paths == null ||
      paths.length != expected.length ||
      !paths.keys.toSet().containsAll(expected) ||
      paths.values.any((value) => value.isEmpty)) {
    throw StateError('native_paths_unavailable');
  }
  // Значения нужны встроенному CPython до первого импорта нативных модулей.
  environment.addAll(paths);
}
