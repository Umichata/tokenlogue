// Test entry point for the separately installed Android vault fixture.
import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final vault = ProfileVault();
  final existing = await vault.exists();
  runApp(
    MaterialApp(
      home: _Fixture(vault: vault, cold: existing),
    ),
  );
}

void require(bool result, String checkpoint) {
  if (!result) throw StateError(checkpoint);
}

Future<void> checkVerifier(
  String expected,
  String excluded,
  String fixtureSlot,
  String stage,
) async {
  // Read only this fixture's own record via its production Android channel.
  // Neither the record nor its verifier is sent to the driver.
  final bytes = await ProfileVault.channel.invokeMethod<Uint8List>('read');
  require(bytes != null, 'missing_record');
  final record = jsonDecode(utf8.decode(bytes!)) as Map<String, dynamic>;
  require(
    record['credentials']?['vsegpt']?['key'] == fixtureSlot,
    '${stage}_profile',
  );
  final salt = record['salt'] as String;
  final verifier = record['verifier'] as String;
  require(await pinDigest(expected, salt) == verifier, '${stage}_expected');
  require(await pinDigest(excluded, salt) != verifier, '${stage}_unexpected');
}

class _Fixture extends StatefulWidget {
  const _Fixture({required this.vault, required this.cold});
  final ProfileVault vault;
  final bool cold;

  @override
  State<_Fixture> createState() => _FixtureState();
}

class _FixtureState extends State<_Fixture> {
  final focus = FocusNode();
  final packet = StringBuffer();
  static final hexDigit = RegExp(r'^[0-9a-f]$');
  String? status;

  Future<void> execute(String input) async {
    if (status != null) return;
    packet.clear();
    setState(() => status = 'Checking');
    try {
      require(
        RegExp(r'^[0-9]{8}[0-9a-f]{56}$').hasMatch(input),
        'fixture_input',
      );
      final payload = input.substring(0, 40);
      final digest = await Sha256().hash(ascii.encode(payload));
      final hex = digest.bytes
          .map((b) => b.toRadixString(16).padLeft(2, '0'))
          .join();
      require(input.substring(40) == hex.substring(0, 24), 'fixture_transport');
      final a = input.substring(0, 4);
      final b = input.substring(4, 8);
      final tag = payload.substring(8);
      require(a != b, 'distinct_pins');
      final slot = 'sk-or-vis-local-fixture-$tag';
      final draft = 'Storage test $tag';
      final vault = widget.vault;
      if (!widget.cold) {
        await vault.register(a, slot, false, canCommit: () => mounted);
        final profile = await vault.unlock(a);
        require(profile != null, 'registration');
        try {
          final store = await ChatStore.open(profile!);
          try {
            final chat = await store.createChat(
              'Vault test',
              Service.vsegpt,
              'fixture',
              false,
            );
            await store.saveDraft(chat, draft, 0);
            await vault.markReady(profile);
          } finally {
            await store.db.close();
          }
        } finally {
          profile!.dispose();
        }
        await checkVerifier(a, b, slot, 'initial');
        require(
          await vault.requestRecovery('Confirm the disposable storage test'),
          'device_confirmation',
        );
        require(await vault.replacePin(b), 'replacement_write');
        await checkVerifier(b, a, slot, 'committed');
        setState(() => status = 'Replacement read back');
      } else {
        // A fresh process has no session, recovery grant or verifier from setup.
        await checkVerifier(b, a, slot, 'cold');
        final profile = await vault.unlock(b);
        require(profile != null, 'cold_unlock');
        try {
          require(profile!.keyFor(Service.vsegpt) == slot, 'original_slot');
          final store = await ChatStore.open(profile);
          try {
            final chat = (await store.chats()).single;
            require(
              chat.title == 'Vault test' && chat.draft == draft,
              'original_draft',
            );
          } finally {
            await store.db.close();
          }
        } finally {
          profile!.dispose();
        }
        setState(() => status = 'Cold verification passed');
      }
    } on StateError catch (error) {
      // Only test-authored checkpoints are suitable for output.
      final checkpoints = {
        'fixture_input',
        'distinct_pins',
        'missing_record',
        'fixture_transport',
        for (final stage in ['initial', 'committed', 'cold'])
          for (final failure in ['profile', 'expected', 'unexpected'])
            '${stage}_$failure',
        'registration',
        'device_confirmation',
        'replacement_write',
        'cold_unlock',
        'original_slot',
        'original_draft',
      };
      setState(
        () => status =
            'Failed: ${checkpoints.contains(error.message) ? error.message : 'state'}',
      );
    } catch (_) {
      setState(() => status = 'Failed: platform or storage operation');
    }
  }

  KeyEventResult receive(FocusNode _, KeyEvent event) {
    if (status != null || event is! KeyDownEvent || event.synthesized) {
      return KeyEventResult.ignored;
    }
    if (event.logicalKey == LogicalKeyboardKey.enter) {
      execute(packet.toString());
    } else {
      final digit = event.logicalKey.keyLabel.toLowerCase();
      if (!hexDigit.hasMatch(digit)) return KeyEventResult.ignored;
      if (packet.length >= 64) {
        packet.clear();
        setState(() => status = 'Failed: fixture_input');
      } else {
        packet.write(digit);
      }
    }
    return KeyEventResult.handled;
  }

  @override
  void dispose() {
    focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Focus(
      autofocus: true,
      focusNode: focus,
      onKeyEvent: receive,
      onFocusChange: (_) {
        if (mounted) setState(() {});
      },
      child: Center(
        child: Text(
          status ??
              (focus.hasPrimaryFocus
                  ? (widget.cold
                        ? 'Cold verification ready'
                        : 'Fresh registration ready')
                  : 'Preparing fixture input'),
        ),
      ),
    ),
  );
}
