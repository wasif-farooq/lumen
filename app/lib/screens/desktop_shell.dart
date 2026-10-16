import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';

import '../api.dart';
import '../app_state.dart';
import '../theme.dart';
import '../widgets/chat_view.dart';
import '../widgets/common.dart';
import '../widgets/preview_panel.dart';
import 'settings_screen.dart';

/// Desktop layout: conversations | chat | file preview.
class DesktopShell extends StatefulWidget {
  const DesktopShell({super.key, required this.state});
  final AppState state;

  @override
  State<DesktopShell> createState() => _DesktopShellState();
}

class _DesktopShellState extends State<DesktopShell> {
  String page = 'chat';
  bool dragging = false;

  static const _settingsTabs = {'settings': 0, 'models': 1, 'index': 2, 'duplicates': 3};

  static const _imageExts = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff', 'heic'};

  /// A photo dropped on the chat: find images that look like it.
  Future<void> _onDrop(DropDoneDetails d) async {
    setState(() => dragging = false);
    final f = d.files.where((f) => _imageExts.contains(f.name.split('.').last.toLowerCase())).firstOrNull;
    if (f == null) return _toast('Drop an image to find similar ones.');
    setState(() => page = 'chat');
    await s.findSimilar(photo: await f.readAsBytes());
  }

  AppState get s => widget.state;

  Future<void> _open(Hit hit, {double start = 0}) async {
    try {
      _toast(await s.api.open(hit.path, start: start));
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _show(Hit hit) async {
    try {
      _toast(await s.api.show(hit.path));
    } catch (e) {
      _toast('$e');
    }
  }

  void _toast(String msg) {
    if (!mounted) return;
    final short = msg.startsWith('NOT OPENED') ? 'Test mode: nothing was opened.' : msg;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(short), duration: const Duration(seconds: 2)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: s,
        builder: (context, _) => LayoutBuilder(builder: (context, c) {
          final showPreview = page == 'chat' && s.selected != null && c.maxWidth >= 1100;
          return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            _Sidebar(state: s, page: page, onPage: (p) => setState(() => page = p)),
            Expanded(
              child: switch (page) {
                'settings' || 'models' || 'index' || 'duplicates' => SettingsScreen(
                    state: s,
                    tab: _settingsTabs[page]!,
                    onTab: (i) => setState(() => page = _settingsTabs.entries.firstWhere((e) => e.value == i).key),
                    onOpen: (h) => _open(h),
                    onShow: _show,
                  ),
                _ => DropTarget(
                    onDragEntered: (_) => setState(() => dragging = true),
                    onDragExited: (_) => setState(() => dragging = false),
                    onDragDone: _onDrop,
                    child: Stack(children: [
                      Column(children: [
                        _ChatHeader(state: s),
                        Expanded(child: ChatView(state: s, onOpen: _open, onShow: _show)),
                        Composer(state: s),
                      ]),
                      if (dragging)
                        Positioned.fill(
                          child: Container(
                            margin: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: C.accentSoft.withValues(alpha: 0.92),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: C.accent, width: 2),
                            ),
                            alignment: Alignment.center,
                            child: const Column(mainAxisSize: MainAxisSize.min, children: [
                              Icon(Icons.image_search, size: 40, color: C.accent),
                              SizedBox(height: 10),
                              Text('Drop a photo to find images like it', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                            ]),
                          ),
                        ),
                    ]),
                  ),
              },
            ),
            if (showPreview)
              Container(
                width: 340,
                decoration: const BoxDecoration(color: C.panel, border: Border(left: BorderSide(color: C.line))),
                child: FileDetails(
                  api: s.api,
                  hit: s.selected!,
                  onOpen: _open,
                  onShow: () => _show(s.selected!),
                  onAsk: s.send,
                  onClose: () => s.select(null),
                  onSimilar: () => s.findSimilar(path: s.selected!.path),
                ),
              ),
          ]);
        }),
      ),
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final title = state.chats.where((c) => c.id == state.chatId).firstOrNull?.title ?? 'New chat';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: C.line))),
      child: Row(children: [
        Expanded(child: Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
        Container(
          height: 32,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(color: const Color(0xFF191D22), borderRadius: BorderRadius.circular(999), border: Border.all(color: C.line2)),
          child: Row(children: [
            StatusDot(size: 7, color: state.status?['models']?['ollama_ok'] == true ? C.green : C.red),
            const SizedBox(width: 8),
            Text(state.model, style: monoStyle(size: 12.5, color: C.text2)),
            Text(' · ${state.agentProvider != 'Ollama' ? state.agentProvider : (state.cpuOnly ? 'CPU' : 'GPU')}',
                style: const TextStyle(fontSize: 13, color: C.text2)),
            if (state.agentCloud) ...[
              const SizedBox(width: 6),
              const Tooltip(message: 'Chat runs on a cloud service', child: Icon(Icons.cloud_outlined, size: 14, color: C.accent)),
            ],
          ]),
        ),
      ]),
    );
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.state, required this.page, required this.onPage});
  final AppState state;
  final String page;
  final void Function(String) onPage;

  @override
  Widget build(BuildContext context) {
    final st = state.status;
    final idx = st?['index'] ?? {};
    final pw = st?['power'] ?? {};
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
                        state.openChat(chat.id);
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
          active: page == 'settings' || page == 'models' || page == 'duplicates',
          onTap: () => onPage(page == 'settings' || page == 'models' || page == 'duplicates' ? 'chat' : 'settings'),
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
                  Text('${pw['on_ac'] == true ? 'Plugged in' : 'On battery'} · ${_cap(pw['mode'] ?? 'auto')}',
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
