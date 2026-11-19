import 'package:synchronized/synchronized.dart';
import 'chat_service.dart';
import 'chat_store.dart';
import 'providers.dart';
import 'vault.dart';

/// Retain already-authorized writes during background locking. The workspace
/// disappears synchronously. Reopening the database waits for this drain.
class Session {
  Session(this.profile, this.store, ProviderApi api)
    : sending = ChatService(store, api);
  final UnlockedProfile profile;
  final ChatStore store;
  final ChatService sending;
  final Lock _drafts = Lock();
  final Set<Future<void>> _active = {};
  bool closing = false;
  Future<void>? _closed;
  Future<void> writeDraft(String chat, String text) {
    if (closing) return Future.error(StateError('locked'));
    return _drafts.synchronized(() async {
      final prev = await store.db.query(
        'drafts',
        columns: ['rev'],
        where: 'chat=?',
        whereArgs: [chat],
      );
      await store.saveDraft(chat, text, prev.firstOrNull?['rev'] as int? ?? 0);
    });
  }

  Future<void> flush() => _drafts.synchronized(() {});
  Future<void> dispatch(PreparedSend prepared, bool confirmed) {
    if (closing) return Future.error(StateError('locked'));
    final result = sending.dispatch(prepared, confirmed: confirmed);
    _active.add(result);
    return result.whenComplete(() => _active.remove(result));
  }

  Future<void> close() {
    if (_closed != null) return _closed!;
    closing = true;
    sending.closed = true;
    sending.invalidate();
    return _closed = () async {
      try {
        await flush();
        await Future.wait(
          _active.toList().map((f) => f.catchError((Object _) {})),
        );
      } finally {
        profile.dispose();
        await store.db.close();
      }
    }();
  }
}
