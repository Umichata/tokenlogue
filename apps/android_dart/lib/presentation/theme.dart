import 'package:flutter/material.dart';

const pageBackground = Color(0xff101923),
    panel = Color(0xff192633),
    elevated = Color(0xff223341),
    input = Color(0xff14212d),
    primary = Color(0xff62d6c3),
    ink = Color(0xffedf3f7),
    muted = Color(0xffb7c5d1),
    border = Color(0xff344859);

ThemeData buildTheme() {
  OutlineInputBorder outline(Color c, double width) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(10),
    borderSide: BorderSide(color: c, width: width),
  );
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: pageBackground,
    dividerColor: border,
    hoverColor: elevated,
    focusColor: border,
    disabledColor: muted,
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        fontSize: 26,
        fontWeight: FontWeight.w600,
        color: ink,
        height: 1.2,
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
      bodyLarge: TextStyle(fontSize: 16, color: ink, height: 1.45),
      bodyMedium: TextStyle(fontSize: 14, color: ink, height: 1.45),
      bodySmall: TextStyle(fontSize: 12, color: muted, height: 1.4),
    ),
    colorScheme: const ColorScheme.dark(
      primary: primary,
      onPrimary: Color(0xff102923),
      secondary: primary,
      surface: panel,
      onSurface: ink,
      onSurfaceVariant: muted,
      outline: border,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(44, 44),
        disabledBackgroundColor: elevated,
        disabledForegroundColor: muted,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: input,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      enabledBorder: outline(border, 1),
      focusedBorder: outline(primary, 2),
    ),
  );
}
