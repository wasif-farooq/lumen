import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import '../../core/models/json.dart';

/// Desktop sidebar: new chat, the chats, Settings, and the Sync tile (index size, power).
class Sidebar extends StatelessWidget {
  const Sidebar({super.key, required this.state, required this.page, required this.onPage});
  final AppState state;
  final String page;
  final void Function(String) onPage;

  @override
  Widget build(BuildContext context) {
    final st = state.status;
    final idx = mapOf(st?['index']);
    final pw = mapOf(st?['power']);
    return Container(
      width: 264,
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 16),
      decoration: const BoxDecoration(color: C.panel, border: Border(right: BorderSide(color: C.line))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Row(children: [Logo(), SizedBox(width: 10), Text('Lumen', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16))]),
        const SizedBox(height: 20),
        FilledButton.icon(
          onPressed: () {
            state.newChat();
            onPage('chat');
          },
          icon: const Icon(Icons.add, size: 18),
          label: const Text('New chat'),
        ),
        const SizedBox(height: 20),
        const Padding(
          padding: EdgeInsets.only(left: 8, bottom: 6),
          child: Text('CHATS', style: TextStyle(fontSize: 12, color: C.muted, letterSpacing: 0.8, fontWeight: FontWeight.w500)),
        ),
        Expanded(
          child: state.chats.isEmpty
              ? const Padding(padding: EdgeInsets.all(8), child: Text('No chats yet.', style: TextStyle(color: C.muted, fontSize: 13)))
              : ListView(children: [
                  for (final chat in state.chats)
                    _ChatTile(
                      chat: chat,
                      active: page == 'chat' && chat.id == state.chatId,
                      onTap: () {
                        unawaited(state.openChat(chat.id));
                        onPage('chat');
                      },
                      onDelete: () => state.deleteChat(chat.id),
                    ),
                ]),
        ),
        const SizedBox(height: 12),
        _NavButton(
          icon: Icons.settings_outlined,
          label: 'Settings',
          active: page == 'settings' || page == 'models',
          onTap: () => onPage(page == 'settings' || page == 'models' ? 'chat' : 'settings'),
        ),
        const SizedBox(height: 8),
        Material(
          color: page == 'index' ? C.raised : const Color(0xFF191D22),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: Color(0xFF2A2F35))),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: () => onPage(page == 'index' ? 'chat' : 'index'),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  StatusDot(color: st?['indexing'] == true ? C.accent : C.green),
                  const SizedBox(width: 8),
                  Text(st?['indexing'] == true ? (st?['index_paused'] == true ? 'Indexing paused' : 'Indexing…') : 'Sync', style: const TextStyle(fontWeight: FontWeight.w500)),
                ]),
                const SizedBox(height: 6),
                Text('${idx['files'] ?? '–'} files · ${idx['captioned'] ?? '–'} images · ${idx['media_indexed'] ?? '–'} videos',
                    style: const TextStyle(fontSize: 13, color: C.text3)),
                const SizedBox(height: 4),
                Row(children: [
                  Icon(pw['on_ac'] == true ? Icons.power_outlined : Icons.battery_std_outlined, size: 15, color: C.text3),
                  const SizedBox(width: 6),
                  Text('${pw['on_ac'] == true ? 'Plugged in' : 'On battery'} · ${_cap('${pw['mode'] ?? 'auto'}')}',
                      style: const TextStyle(fontSize: 13, color: C.text3)),
                ]),
              ]),
            ),
          ),
        ),
      ]),
    );
  }

  static String _cap(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

class _NavButton extends StatelessWidget {
  const _NavButton({required this.icon, required this.label, required this.active, required this.onTap});
  final IconData icon;
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: active ? C.raised : Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10), side: const BorderSide(color: Color(0xFF2A2F35))),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
          child: SizedBox(
            height: 44,
            child: Row(children: [
              const SizedBox(width: 14),
              Icon(icon, size: 18, color: active ? C.text : C.text2),
              const SizedBox(width: 10),
              Text(label, style: TextStyle(color: active ? C.text : C.text2)),
            ]),
          ),
        ),
      );
}

class _ChatTile extends StatefulWidget {
  const _ChatTile({required this.chat, required this.active, required this.onTap, required this.onDelete});
  final Chat chat;
  final bool active;
  final VoidCallback onTap, onDelete;

  @override
  State<_ChatTile> createState() => _ChatTileState();
}

class _ChatTileState extends State<_ChatTile> {
  bool hover = false;

  @override
  Widget build(BuildContext context) => MouseRegion(
        onEnter: (_) => setState(() => hover = true),
        onExit: (_) => setState(() => hover = false),
        child: Material(
          color: widget.active ? C.raised : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
          child: InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: widget.onTap,
            child: SizedBox(
              height: 42,
              child: Row(children: [
                const SizedBox(width: 12),
                Expanded(
                  child: Text(widget.chat.title,
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: widget.active ? C.text : C.text2)),
                ),
                if (hover)
                  IconButton(
                    tooltip: 'Delete chat',
                    visualDensity: VisualDensity.compact,
                    onPressed: widget.onDelete,
                    icon: const Icon(Icons.delete_outline, size: 16, color: C.muted),
                  ),
              ]),
            ),
          ),
        ),
      );
}
