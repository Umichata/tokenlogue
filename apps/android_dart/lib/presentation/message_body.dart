import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:markdown/markdown.dart' as md;
import 'theme.dart';

/// Keep the author's marker, including nonconsecutive numbers and closing parentheses.
class _NumberedItem extends md.BlockSyntax {
  @override
  final pattern = RegExp(r'^([ \t]*[0-9]{1,9}[.)])[ \t]+(.+)$');
  @override
  md.Node parse(md.BlockParser parser) {
    final item = pattern.firstMatch(parser.current.content)!;
    parser.advance();
    return md.Element('p', [
      md.Text('${item[1]} '),
      md.UnparsedContent(item[2]!),
    ]);
  }
}

class MessageBody extends StatelessWidget {
  const MessageBody({super.key, required this.source, required this.copyLabel});
  final String source, copyLabel;
  List<InlineSpan> _inline(List<md.Node> nodes) {
    return [
      for (final n in nodes)
        if (n is md.Element)
          TextSpan(
            style: TextStyle(
              fontWeight: n.tag == 'strong' ? FontWeight.bold : null,
              fontStyle: n.tag == 'em' ? FontStyle.italic : null,
              fontFamily: n.tag == 'code' ? 'monospace' : null,
            ),
            children: n.tag == 'img'
                ? [TextSpan(text: n.attributes['alt'] ?? '')]
                : _inline(n.children ?? []),
          )
        else
          TextSpan(text: n.textContent),
    ];
  }

  Widget _block(md.Node n) {
    if (n is! md.Element) return SelectableText(n.textContent);
    if (n.tag == 'pre') {
      final code = n.textContent;
      return Container(
        color: pageBackground,
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Align(
              alignment: Alignment.centerRight,
              child: IconButton(
                tooltip: copyLabel,
                icon: const Icon(Icons.copy),
                onPressed: () => Clipboard.setData(ClipboardData(text: code)),
              ),
            ),
            SelectableText(
              code,
              style: const TextStyle(fontFamily: 'monospace'),
            ),
          ],
        ),
      );
    }
    if (n.tag == 'ul' || n.tag == 'ol') {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (i, child) in (n.children ?? <md.Node>[]).indexed)
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(n.tag == 'ul' ? '•  ' : '${i + 1}. '),
                Expanded(child: _block(child)),
              ],
            ),
        ],
      );
    }
    if (n.tag == 'blockquote') {
      return Container(
        decoration: const BoxDecoration(
          border: Border(left: BorderSide(color: primary, width: 2)),
        ),
        padding: const EdgeInsets.only(left: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: (n.children ?? []).map(_block).toList(),
        ),
      );
    }
    final heading = RegExp('^h[1-6]\$').hasMatch(n.tag);
    return SelectableText.rich(
      TextSpan(
        style: TextStyle(
          fontSize: heading ? 22 : 16,
          fontWeight: heading ? FontWeight.bold : null,
        ),
        children: _inline(n.children ?? []),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final nodes = md.Document(
      encodeHtml: false,
      blockSyntaxes: [_NumberedItem()],
      withDefaultInlineSyntaxes: false,
      inlineSyntaxes: [
        md.CodeSyntax(),
        md.EmphasisSyntax.asterisk(),
        md.EmphasisSyntax.underscore(),
      ],
    ).parseLines(source.split('\n'));
    return Column(
      spacing: 8,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: nodes.map(_block).toList(),
    );
  }
}
