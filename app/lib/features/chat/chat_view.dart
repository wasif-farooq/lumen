import 'package:flutter/services.dart';
import 'package:flutter/material.dart';

import '../../shared/widgets/photo_picker.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'results.dart';
import '../../core/format.dart';

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
    if (s.events.isEmpty) return _Welcome(onPick: s.send, compact: widget.compact);
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
        return _UserBubble(text: e.text, compact: widget.compact, image: image);
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
        return _StatusRow(
          icon: e.data['dry_run'] == true ? Icons.info_outline : Icons.check_circle_outline,
          color: e.data['dry_run'] == true ? C.accent : C.green,
          text: e.data['message'] ?? e.data['summary'] ?? 'Done',
          trailing: id == null || undone
              ? null
              : TextButton.icon(onPressed: () => s.undo(id), icon: const Icon(Icons.undo, size: 16), label: const Text('Undo')),
        );
      case 'action_cancelled':
        return _StatusRow(icon: Icons.block, color: C.muted, text: 'Cancelled: ${e.data['summary']}');
      case 'action_failed':
        return _StatusRow(icon: Icons.error_outline, color: C.red, text: 'Failed: ${e.data['error']}');
      case 'undone':
        return _StatusRow(icon: Icons.undo, color: C.blue, text: 'Undone. ${e.text}');
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

class _StatusRow extends StatelessWidget {
  const _StatusRow({required this.icon, required this.color, required this.text, this.trailing});
  final IconData icon;
  final Color color;
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Row(children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 13, color: C.text2))),
        ?trailing,
      ]);
}

/// A change the agent wants to make: what, where, and Approve / Cancel.
class ApprovalCard extends StatelessWidget {
  const ApprovalCard({super.key, required this.plan, required this.pending, required this.answer, required this.busy, required this.onAnswer});
  final Map<String, dynamic> plan;
  final bool pending, busy;
  final bool? answer;
  final void Function(bool approved) onAnswer;

  @override
  Widget build(BuildContext context) {
    final op = plan['op'] as String? ?? '';
    final (icon, title) = switch (op) {
      'create_folder' => (Icons.create_new_folder_outlined, 'Create a folder'),
      'create_file' => (Icons.note_add_outlined, 'Create a file'),
      'copy' => (Icons.copy_all_outlined, 'Copy'),
      'move' => (Icons.drive_file_move_outline, (plan['summary'] ?? '').toString().startsWith('Rename') ? 'Rename' : 'Move'),
      _ => (Icons.edit_outlined, 'Change'),
    };
    final size = plan['size'] is int && op != 'create_folder' ? ' · ${humanSize(plan['size'])}' : '';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: pending ? C.accentSoft : C.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: pending ? C.accent : C.line, width: pending ? 1.5 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 20, color: C.accent),
          const SizedBox(width: 10),
          Text('$title$size', style: const TextStyle(fontWeight: FontWeight.w600)),
          const Spacer(),
          if (!pending)
            Text(answer == true ? 'Approved' : (answer == false ? 'Cancelled' : ''), style: const TextStyle(fontSize: 12.5, color: C.muted)),
        ]),
        const SizedBox(height: 10),
        if (plan['src'] != null) _PathLine(label: 'From', path: plan['src']),
        if (plan['dst'] != null) _PathLine(label: plan['src'] != null ? 'To' : 'Path', path: plan['dst']),
        if ((plan['preview'] ?? '').toString().isNotEmpty) ...[
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: C.bg, borderRadius: BorderRadius.circular(8)),
            child: Text(plan['preview'], style: monoStyle(size: 12, color: C.text2), maxLines: 8, overflow: TextOverflow.ellipsis),
          ),
        ],
        if (pending) ...[
          const SizedBox(height: 14),
          Row(children: [
            FilledButton(onPressed: busy ? null : () => onAnswer(true), child: const Text('Approve')),
            const SizedBox(width: 8),
            OutlinedButton(onPressed: busy ? null : () => onAnswer(false), child: const Text('Cancel')),
            const SizedBox(width: 12),
            const Expanded(child: Text('Never overwrites. You can undo it after.', style: TextStyle(fontSize: 12, color: C.muted))),
          ]),
        ],
      ]),
    );
  }
}

class _PathLine extends StatelessWidget {
  const _PathLine({required this.label, required this.path});
  final String label, path;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 44, child: Text(label, style: const TextStyle(fontSize: 13, color: C.muted))),
          Expanded(child: SelectableText(shortPath(path), style: monoStyle(size: 12.5, color: C.text))),
        ]),
      );
}

/// Copies a message as plain text (markdown markers removed) and confirms it.
Future<void> copyText(BuildContext context, String text) async {
  final plain = text.replaceAll('**', '').replaceAll('`', '');
  await Clipboard.setData(ClipboardData(text: plain));
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Copied'), duration: Duration(seconds: 1)));
  }
}

class CopyButton extends StatefulWidget {
  const CopyButton({super.key, required this.text});
  final String text;

  @override
  State<CopyButton> createState() => _CopyButtonState();
}

class _CopyButtonState extends State<CopyButton> {
  bool copied = false;

  @override
  Widget build(BuildContext context) => IconButton(
        tooltip: copied ? 'Copied' : 'Copy',
        visualDensity: VisualDensity.compact,
        iconSize: 16,
        onPressed: () async {
          await Clipboard.setData(ClipboardData(text: widget.text.replaceAll('**', '').replaceAll('`', '')));
          setState(() => copied = true);
          await Future.delayed(const Duration(milliseconds: 1500));
          if (mounted) setState(() => copied = false);
        },
        icon: Icon(copied ? Icons.check : Icons.content_copy_outlined, color: copied ? C.green : C.muted),
      );
}

/// The user's message; a copy button appears on hover (desktop), long-press copies (phone).
class _UserBubble extends StatefulWidget {
  const _UserBubble({required this.text, required this.compact, this.image});
  final String text;
  final bool compact;
  final Widget? image; // a photo the user searched with

  @override
  State<_UserBubble> createState() => _UserBubbleState();
}

class _UserBubbleState extends State<_UserBubble> {
  bool hover = false;

  @override
  Widget build(BuildContext context) => MouseRegion(
        onEnter: (_) => setState(() => hover = true),
        onExit: (_) => setState(() => hover = false),
        child: Row(mainAxisAlignment: MainAxisAlignment.end, crossAxisAlignment: CrossAxisAlignment.center, children: [
          if (!widget.compact)
            AnimatedOpacity(opacity: hover ? 1 : 0, duration: const Duration(milliseconds: 120), child: CopyButton(text: widget.text)),
          const SizedBox(width: 4),
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: widget.compact ? 300 : 560),
              child: GestureDetector(
                onLongPress: widget.compact ? () => copyText(context, widget.text) : null,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: const BoxDecoration(
                    color: C.bubble,
                    borderRadius: BorderRadius.only(topLeft: Radius.circular(14), topRight: Radius.circular(14), bottomLeft: Radius.circular(14), bottomRight: Radius.circular(4)),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
                    if (widget.image != null) ...[
                      ClipRRect(borderRadius: BorderRadius.circular(8), child: SizedBox(width: 180, height: 130, child: widget.image)),
                      const SizedBox(height: 8),
                    ],
                    widget.compact ? Text(widget.text, style: const TextStyle(fontSize: 14.5)) : SelectableText(widget.text, style: const TextStyle(fontSize: 14.5)),
                  ]),
                ),
              ),
            ),
          ),
        ]),
      );
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.onPick, required this.compact});
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

/// Message box with send button.
class Composer extends StatefulWidget {
  const Composer({super.key, required this.state, this.compact = false});
  final AppState state;
  final bool compact;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  final _ctrl = TextEditingController();
  final _focus = FocusNode();

  Future<void> _attach() async {
    final bytes = await pickPhoto(context);
    if (bytes != null) widget.state.findSimilar(photo: bytes);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send() {
    final text = _ctrl.text;
    if (text.trim().isEmpty || widget.state.busy || widget.state.pendingApproval != null) return;
    _ctrl.clear();
    widget.state.send(text);
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final busy = widget.state.busy;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 820),
        child: Padding(
          padding: EdgeInsets.fromLTRB(widget.compact ? 12 : 28, 0, widget.compact ? 12 : 28, widget.compact ? 12 : 10),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(
              padding: const EdgeInsets.fromLTRB(16, 6, 6, 6),
              decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: C.line2)),
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Expanded(
                  child: CallbackShortcuts(
                    bindings: {const SingleActivator(LogicalKeyboardKey.enter): _send},
                    child: TextField(
                      controller: _ctrl,
                      focusNode: _focus,
                      autofocus: !widget.compact,
                      minLines: 1,
                      maxLines: 5,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                      style: const TextStyle(fontSize: 15),
                      decoration: InputDecoration(
                        hintText: widget.state.pendingApproval != null
                            ? 'Approve or cancel the change above first'
                            : (widget.compact ? 'Ask about your files…' : 'Ask to find, open or explain a file…'),
                        contentPadding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Search with a photo',
                  onPressed: busy ? null : _attach,
                  icon: const Icon(Icons.add_photo_alternate_outlined, color: C.text2),
                ),
                const SizedBox(width: 4),
                IconButton.filled(
                  tooltip: 'Send',
                  onPressed: busy ? null : _send,
                  style: IconButton.styleFrom(
                    backgroundColor: C.accent,
                    foregroundColor: C.onAccent,
                    disabledBackgroundColor: C.raised,
                    minimumSize: const Size(44, 44),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  icon: busy
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: C.text3))
                      : const Icon(Icons.arrow_upward_rounded),
                ),
              ]),
            ),
            if (!widget.compact)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Icon(widget.state.agentCloud || widget.state.visionCloud ? Icons.cloud_outlined : Icons.lock_outline,
                      size: 13, color: widget.state.agentCloud ? C.accent : C.muted),
                  const SizedBox(width: 6),
                  // Only promise privacy while it is true: a cloud provider sees what it is sent
                  Flexible(
                    child: Text(
                      widget.state.agentCloud
                          ? 'Chat runs on ${widget.state.agentProvider}: your questions and the files it reads are sent there.'
                          : widget.state.visionCloud
                              ? 'Chat runs on this laptop. Images are described by ${widget.state.visionProvider} while indexing.'
                              : 'Runs on this laptop. Nothing leaves it.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: widget.state.agentCloud ? C.accent : C.muted),
                    ),
                  ),
                ]),
              ),
          ]),
        ),
      ),
    );
  }
}
