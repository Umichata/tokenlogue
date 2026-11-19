import 'package:sqflite/sqflite.dart';

Future<String> profileDatabasePath() async =>
    '${await getDatabasesPath()}/tokenlogue-dart-v1.db';

/// Recovery checks the registration against the existing database without
/// migrating, creating or decrypting any chat records.
Future<String?> existingProfileBinding() async {
  final path = await profileDatabasePath();
  if (!await databaseExists(path)) return null;
  final db = await openDatabase(path, readOnly: true, singleInstance: false);
  try {
    final rows = await db.query('profile', columns: ['id'], limit: 2);
    return rows.length == 1 ? rows.single['id'] as String? : null;
  } finally {
    await db.close();
  }
}
