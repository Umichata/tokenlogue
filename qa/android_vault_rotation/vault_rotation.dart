// Test entry point for the separately installed Android vault fixture.
import 'dart:convert';

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

Future<void> checkVerifier(String expected, String excluded) async {
  // Read only this fixture's own record via its production Android channel.
  // Neither the record nor its verifier is sent to the driver.
  final bytes = await ProfileVault.channel.invokeMethod<Uint8List>('read');
  require(bytes != null, 'missing_record');
  final record = jsonDecode(utf8.decode(bytes!)) as Map<String, dynamic>;
  final salt = record['salt'] as String;
  final verifier = record['verifier'] as String;
  require(await pinDigest(expected, salt) == verifier, 'expected_verifier');
  require(await pinDigest(excluded, salt) != verifier, 'unexpected_verifier');
}

class _Fixture extends StatefulWidget {
  const _Fixture({required this.vault, required this.cold});
  final ProfileVault vault;
  final bool cold;

  @override
  State<_Fixture> createState() => _FixtureState();
}

class _FixtureState extends State<_Fixture> {
  final controller = TextEditingController();
  String? status;

  Future<void> execute(String input) async {
    if (status != null) return;
    controller.clear();
    FocusScope.of(context).unfocus();
    setState(() => status = 'Checking');
    try {
      require(
        RegExp(r'^[0-9]{8}[0-9a-f]{32}$').hasMatch(input),
        'fixture_input',
      );
      final a = input.substring(0, 4);
      final b = input.substring(4, 8);
      final tag = input.substring(8);
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
        await checkVerifier(a, b);
        require(
          await vault.requestRecovery('Confirm the disposable storage test'),
          'device_confirmation',
        );
        require(await vault.replacePin(b), 'replacement_write');
        setState(() => status = 'Replacement committed');
      } else {
        // A fresh process has no session, recovery grant or verifier from setup.
        await checkVerifier(b, a);
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
      const checkpoints = {
        'fixture_input',
        'distinct_pins',
        'missing_record',
        'expected_verifier',
        'unexpected_verifier',
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

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Text(
              status ??
                  (widget.cold
                      ? 'Cold verification ready'
                      : 'Fresh registration ready'),
            ),
            if (status == null)
              TextField(
                controller: controller,
                autofocus: true,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                enableIMEPersonalizedLearning: false,
                keyboardType: TextInputType.visiblePassword,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(
                  labelText: 'Disposable fixture',
                ),
                onSubmitted: execute,
              ),
          ],
        ),
      ),
    ),
  );
}
