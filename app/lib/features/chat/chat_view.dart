import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'approval_card.dart';
import 'copy.dart';
import 'message_parts.dart';
import 'results.dart';
import 'user_bubble.dart';
import 'welcome.dart';

/// The conversation: user bubbles, tool chips, result cards and answers.
class ChatView extends StatefulWidget {
  const ChatView({super.key, required this.state, required this.onOpen, required this.onShow, this.compact = false, this.onHitTap});
  final AppState state;
  final HitAction onOpen;
  final void Function(Hit hit) onShow;
  final void Function(Hit hit)? onHitTap; // mobile: open the result sheet
  final bool compact;

  @override
  State<ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<ChatView> {
  final _scroll = ScrollController();
  int _lastCount = 0;
  final _expanded = <int>{};

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _autoScroll() {
    if (widget.state.events.length == _lastCount) return;
    _lastCount = widget.state.events.length;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.state;
    _autoScroll();
    if (s.events.isEmpty) return Welcome(onPick: s.send, compact: widget.compact);
    final pad = widget.compact ? 16.0 : 28.0;
    return ListView(
      controller: _scroll,
      padding: EdgeInsets.fromLTRB(pad, pad, pad, 16),
      children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 820),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              for (final (i, e) in s.events.indexed) ...[
                _event(i, e),
                SizedBox(height: e.type == 'tool_call' ? 10 : 18),
              ],
              if (s.working != null)
                Row(children: [
                  const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: C.accent)),
                  const SizedBox(width: 10),
                  Text(s.working!, style: const TextStyle(color: C.text3)),
                ]),
            ]),
          ),
        ),
      ],
    );
  }

  Widget _event(int i, ChatEvent e) {
    final s = widget.state;
    switch (e.type) {
      case 'user':
        final image = e.upload != null
            ? Image.network(s.api.uploadUrl(e.upload!), headers: s.api.headers, fit: BoxFit.cover, errorBuilder: (_, _, _) => const SizedBox())
            : (e.imagePath != null ? ApiImage(api: s.api, path: e.imagePath!, w: 320) : null);
        return UserBubble(text: e.text, compact: widget.compact, image: image);
      case 'tool_call':
        return ToolChip(name: e.data['name'] ?? '', args: Map<String, dynamic>.from(e.data['args'] ?? {}));
      case 'results':
        final hits = e.hits;
        if (hits.isEmpty) return const Text('No files matched.', style: TextStyle(color: C.text3));
        final showAll = _expanded.contains(i);
        final visible = showAll ? hits : hits.take(3).toList();
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (final h in visible) ...[
            ResultCard(
              hit: h,
              api: s.api,
              compact: widget.compact,
              selected: !widget.compact && s.selected?.path == h.path,
              onSelect: () => widget.onHitTap != null ? widget.onHitTap!(h) : s.select(h),
              onOpen: widget.onOpen,
              onShow: () => widget.onShow(h),
              onSimilar: () => s.findSimilar(path: h.path),
            ),
            const SizedBox(height: 8),
          ],
          if (hits.length > 3)
            TextButton(
              onPressed: () => setState(() => showAll ? _expanded.remove(i) : _expanded.add(i)),
              child: Text(showAll ? 'Show fewer' : 'Show ${hits.length - 3} more results'),
            ),
        ]);
      case 'opened':
        final dry = e.data['dry_run'] == true;
        final start = (e.data['start_seconds'] as num?)?.toDouble() ?? 0;
        return Row(children: [
          Icon(dry ? Icons.info_outline : Icons.check, size: 16, color: dry ? C.accent : C.green),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '${dry ? 'Test mode, not opened: ' : 'Opened on ${s.host}: '}${(e.data['path'] as String).split('/').last}${start > 0 ? ' at ${clock(start)}' : ''}',
              style: const TextStyle(color: C.text2, fontSize: 13),
            ),
          ),
        ]);
      case 'approval':
        return ApprovalCard(
          plan: e.data,
          pending: identical(s.pendingApproval, e),
          answer: _answerAfter(i),
          busy: s.busy,
          onAnswer: s.answerApproval,
        );
      case 'approval_answer':
        return const SizedBox.shrink();
      case 'action_done':
        final id = e.data['id'] as String?;
        final undone = s.events.any((x) => x.type == 'undone' && x.data['action_id'] == id);
        return StatusRow(
          icon: e.data['dry_run'] == true ? Icons.info_outline : Icons.check_circle_outline,
          color: e.data['dry_run'] == true ? C.accent : C.green,
          text: e.data['message'] ?? e.data['summary'] ?? 'Done',
          trailing: id == null || undone
              ? null
              : TextButton.icon(onPressed: () => s.undo(id), icon: const Icon(Icons.undo, size: 16), label: const Text('Undo')),
        );
      case 'action_cancelled':
        return StatusRow(icon: Icons.block, color: C.muted, text: 'Cancelled: ${e.data['summary']}');
      case 'action_failed':
        return StatusRow(icon: Icons.error_outline, color: C.red, text: 'Failed: ${e.data['error']}');
      case 'undone':
        return StatusRow(icon: Icons.undo, color: C.blue, text: 'Undone. ${e.text}');
      case 'answer':
        return GestureDetector(
          onLongPress: widget.compact ? () => copyText(context, e.text) : null,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            AnswerText(e.text),
            const SizedBox(height: 4),
            CopyButton(text: e.text),
          ]),
        );
      case 'error':
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: const Color(0xFF2A1A1A), borderRadius: BorderRadius.circular(10), border: Border.all(color: const Color(0xFF4A2A2A))),
          child: Text(e.text, style: const TextStyle(color: C.red)),
        );
      default:
        return const SizedBox.shrink();
    }
  }
}

extension on _ChatViewState {
  /// How an approval request was answered: true / false, or null while still waiting.
  bool? _answerAfter(int i) {
    for (final e in widget.state.events.skip(i + 1)) {
      if (e.type == 'approval_answer') return e.data['approved'] == true;
      if (e.type == 'approval') return null;
    }
    return null;
  }
}
