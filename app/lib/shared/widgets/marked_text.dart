import 'package:flutter/material.dart';

import '../theme.dart';

const markStyle = TextStyle(color: C.markFg, backgroundColor: C.markBg);

/// The words of a search hit's snippet ("…of [Taxpayers] Total [Tax]…" -> Taxpayers, Tax).
List<String> snippetTerms(String snippet) =>
    {for (final m in RegExp(r'\[([^\]]+)\]').allMatches(snippet)) m.group(1)!.trim()}.where((t) => t.length > 1).toList();

/// [text] as spans with every one of [terms] marked (any case).
List<InlineSpan> markTerms(String text, List<String> terms, {TextStyle? style}) {
  final words = [for (final t in terms) if (t.trim().isNotEmpty) RegExp.escape(t.trim())];
  if (words.isEmpty) return [TextSpan(text: text, style: style)];
  final re = RegExp(words.join('|'), caseSensitive: false);
  final spans = <InlineSpan>[];
  var last = 0;
  for (final m in re.allMatches(text)) {
    if (m.start > last) spans.add(TextSpan(text: text.substring(last, m.start), style: style));
    spans.add(TextSpan(text: m.group(0), style: (style ?? const TextStyle()).merge(markStyle)));
    last = m.end;
  }
  if (last < text.length) spans.add(TextSpan(text: text.substring(last), style: style));
  return spans;
}

/// Text with search words marked; selectable.
class MarkedText extends StatelessWidget {
  const MarkedText(this.text, {super.key, this.terms = const [], this.style});
  final String text;
  final List<String> terms;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) => SelectableText.rich(TextSpan(children: markTerms(text, terms)), style: style);
}
