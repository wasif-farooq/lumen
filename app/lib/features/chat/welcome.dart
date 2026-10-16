import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';

/// An empty chat: what Lumen can do, with example questions to start from.
class Welcome extends StatelessWidget {
  const Welcome({super.key, required this.onPick, required this.compact});
  final void Function(String) onPick;
  final bool compact;

  static const ideas = [
    'Find my CV',
    'PDFs I changed this month',
    'Find my identity card pictures',
    'Videos longer than 30 minutes',
    'Where is my degree certificate?',
    'What does the ERP process flows PDF cover?',
  ];

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Logo(size: 44),
              const SizedBox(height: 18),
              Text('What are you looking for?', style: TextStyle(fontSize: compact ? 22 : 26, fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              const Text(
                'Ask in your own words. I search names, the text inside documents, what images and videos show, and what is said in videos.',
                textAlign: TextAlign.center,
                style: TextStyle(color: C.text3),
              ),
              const SizedBox(height: 24),
              Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [
                for (final idea in ideas)
                  ActionChip(
                    label: Text(idea),
                    onPressed: () => onPick(idea),
                    backgroundColor: C.surface,
                    side: const BorderSide(color: C.line2),
                    labelStyle: const TextStyle(color: C.text2, fontSize: 13),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
                  ),
              ]),
            ]),
          ),
        ),
      );
}
