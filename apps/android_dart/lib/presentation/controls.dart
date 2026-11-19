import 'package:flutter/material.dart';
import 'theme.dart';

typedef Translate = String Function(String);
String interpolate(String text, Map<String, Object?> values) {
  for (final item in values.entries) {
    text = text.replaceAll('{${item.key}}', '${item.value}');
  }
  return text;
}

Widget panelCard(List<Widget> children, {EdgeInsetsGeometry? padding}) =>
    Container(
      padding: padding ?? const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: panel,
        border: Border.all(color: border),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        spacing: 12,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
    );

Future<bool> confirm(
  BuildContext context,
  String title,
  String body,
  String cancel,
  String accept,
) => showDialog<bool>(
  context: context,
  builder: (ctx) => AlertDialog(
    scrollable: true,
    title: Text(title),
    content: Text(body),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(ctx, false),
        child: Text(cancel),
      ),
      FilledButton(
        onPressed: () => Navigator.pop(ctx, true),
        child: Text(accept),
      ),
    ],
  ),
).then((v) => v == true);

class SecretField extends StatefulWidget {
  const SecretField({
    super.key,
    required this.controller,
    required this.label,
    required this.t,
    required this.changed,
    this.enabled = true,
    this.focus = false,
    this.hint,
  });
  final TextEditingController controller;
  final String label;
  final String? hint;
  final Translate t;
  final ValueChanged<String> changed;
  final bool enabled, focus;
  @override
  State<SecretField> createState() => _SecretFieldState();
}

class _SecretFieldState extends State<SecretField> {
  bool hidden = true;
  @override
  Widget build(BuildContext context) => TextField(
    controller: widget.controller,
    obscureText: hidden,
    enabled: widget.enabled,
    autocorrect: false,
    enableSuggestions: false,
    enableIMEPersonalizedLearning: false,
    keyboardType: TextInputType.visiblePassword,
    autofocus: widget.focus,
    onChanged: widget.changed,
    decoration: InputDecoration(
      labelText: widget.label,
      hintText: widget.hint,
      suffixIcon: IconButton(
        tooltip: widget.t(hidden ? 'providers.reveal' : 'providers.conceal'),
        icon: Icon(hidden ? Icons.visibility : Icons.visibility_off),
        onPressed: () => setState(() => hidden = !hidden),
      ),
    ),
  );
}

class BrandLoader extends StatelessWidget {
  const BrandLoader({super.key, this.size = 26});
  final double size;
  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.disableAnimationsOf(context);
    return Center(
      child: Image.asset(
        reduce
            ? 'assets/branding/tokenlogue-loading-static.png'
            : 'assets/branding/tokenlogue-loading.webp',
        width: size,
        height: size,
        excludeFromSemantics: true,
      ),
    );
  }
}
