import 'package:flutter/material.dart';

import '../theme.dart';
import 'marked_text.dart';

/// Markdown, formatted: headings, lists, quotes, code blocks, rules, and **bold**, *italic*,
/// `code` and [links](…) (shown as text). Small on purpose: notes and README-style files.
class MarkdownView extends StatelessWidget {
  const MarkdownView(this.text, {super.key, this.terms = const []});
  final String text;
  final List<String> terms; // search words to mark

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [for (final b in _blocks(text)) Padding(padding: const EdgeInsets.only(bottom: 10), child: _block(b))],
      );

  Widget _block(_Block b) {
    switch (b.kind) {
      case 'h':
        final size = const [24.0, 20.0, 17.0, 15.5][(b.level - 1).clamp(0, 3)];
        return Text.rich(TextSpan(children: _inline(b.text)), style: TextStyle(fontSize: size, fontWeight: FontWeight.w600, height: 1.3));
      case 'code':
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(8)),
          child: SelectableText.rich(TextSpan(children: markTerms(b.text, terms)), style: monoStyle(size: 13, color: C.text)),
        );
      case 'quote':
        return Container(
          padding: const EdgeInsets.only(left: 12),
          decoration: const BoxDecoration(border: Border(left: BorderSide(color: C.line2, width: 3))),
          child: Text.rich(TextSpan(children: _inline(b.text)), style: const TextStyle(color: C.text2, height: 1.5)),
        );
      case 'rule':
        return const Divider(color: C.line2);
      case 'li':
        return Padding(
          padding: EdgeInsets.only(left: 18.0 * b.level),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: 22, child: Text(b.marker, style: const TextStyle(color: C.muted, height: 1.5))),
            Expanded(child: Text.rich(TextSpan(children: _inline(b.text)), style: const TextStyle(height: 1.5))),
          ]),
        );
      default:
        return SelectableText.rich(TextSpan(children: _inline(b.text)), style: const TextStyle(fontSize: 14.5, height: 1.55));
    }
  }

  /// **bold**, *italic*, `code`, [link](url) -> text; search words marked in the plain parts.
  List<InlineSpan> _inline(String text) {
    final re = RegExp(r'\*\*(.+?)\*\*|(?<!\*)\*(?!\s)(.+?)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]*)\)');
    final out = <InlineSpan>[];
    var last = 0;
    for (final m in re.allMatches(text)) {
      if (m.start > last) out.addAll(markTerms(text.substring(last, m.start), terms));
      if (m.group(1) != null) {
        out.addAll(markTerms(m.group(1)!, terms, style: const TextStyle(fontWeight: FontWeight.w700)));
      } else if (m.group(2) != null) {
        out.addAll(markTerms(m.group(2)!, terms, style: const TextStyle(fontStyle: FontStyle.italic)));
      } else if (m.group(3) != null) {
        out.add(TextSpan(text: m.group(3), style: monoStyle(size: 13, color: C.text2)));
      } else {
        out.addAll(markTerms(m.group(4)!, terms, style: const TextStyle(color: C.blue, decoration: TextDecoration.underline)));
      }
      last = m.end;
    }
    if (last < text.length) out.addAll(markTerms(text.substring(last), terms));
    return out;
  }
}

class _Block {
  _Block(this.kind, this.text, {this.level = 1, this.marker = ''});
  final String kind; // h | p | li | code | quote | rule
  String text;
  final int level;
  final String marker;
}

List<_Block> _blocks(String text) {
  final out = <_Block>[];
  final lines = text.replaceAll('\r\n', '\n').split('\n');
  var i = 0;
  while (i < lines.length) {
    final line = lines[i];
    final trimmed = line.trim();
    if (trimmed.startsWith('```')) {
      final code = <String>[];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        code.add(lines[i++]);
      }
      i++; // the closing fence
      out.add(_Block('code', code.join('\n')));
      continue;
    }
    if (trimmed.isEmpty) {
      i++;
      continue;
    }
    final heading = RegExp(r'^(#{1,6})\s+(.*)$').firstMatch(trimmed);
    final item = RegExp(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$').firstMatch(line);
    if (heading != null) {
      out.add(_Block('h', heading.group(2)!.replaceAll(RegExp(r'\s*#+$'), ''), level: heading.group(1)!.length));
    } else if (RegExp(r'^([-*_])(\s*\1){2,}$').hasMatch(trimmed)) {
      out.add(_Block('rule', ''));
    } else if (item != null) {
      final number = RegExp(r'\d').hasMatch(item.group(2)!);
      out.add(_Block('li', item.group(3)!, level: item.group(1)!.length ~/ 2, marker: number ? item.group(2)! : '•'));
    } else if (trimmed.startsWith('>')) {
      final quote = trimmed.replaceFirst(RegExp(r'^>\s?'), '');
      if (out.isNotEmpty && out.last.kind == 'quote') {
        out.last.text += ' $quote';
      } else {
        out.add(_Block('quote', quote));
      }
    } else if (out.isNotEmpty && out.last.kind == 'p' && i > 0 && lines[i - 1].trim().isNotEmpty) {
      out.last.text += ' $trimmed'; // a paragraph continues on the next line
    } else {
      out.add(_Block('p', trimmed));
    }
    i++;
  }
  return out;
}
