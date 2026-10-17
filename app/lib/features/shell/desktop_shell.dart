import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import '../chat/chat_view.dart';
import '../chat/composer.dart';
import '../planner/planner_screen.dart';
import '../preview/file_details.dart';
import '../settings/settings_screen.dart';
import 'chat_header.dart';
import 'sidebar.dart';

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

  static const _settingsTabs = {'settings': 0, 'models': 1, 'index': 2};

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

  Future<void> _open(Hit hit, {double start = 0}) =>
      runGuarded<String>(context, () => s.api.open(hit.path, start: start), failure: 'Could not open ${hit.name}', success: _said);

  Future<void> _show(Hit hit) =>
      runGuarded<String>(context, () => s.api.show(hit.path), failure: 'Could not show ${hit.name}', success: _said);

  /// What the server says it did ("Opened …"); in test mode nothing is opened.
  static String _said(String msg) => msg.startsWith('NOT OPENED') ? 'Test mode: nothing was opened.' : msg;

  void _toast(String msg) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), duration: const Duration(seconds: 2)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: s,
        builder: (context, _) => LayoutBuilder(builder: (context, c) {
          final showPreview = page == 'chat' && s.selected != null && c.maxWidth >= 1100;
          return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Sidebar(state: s, page: page, onPage: (p) => setState(() => page = p)),
            Expanded(
              child: switch (page) {
                'planner' => PlannerScreen(state: s),
                'settings' || 'models' || 'index' => SettingsScreen(
                    state: s,
                    tab: _settingsTabs[page]!,
                    onTab: (i) => setState(() => page = _settingsTabs.entries.firstWhere((e) => e.value == i).key),
                  ),
                _ => DropTarget(
                    onDragEntered: (_) => setState(() => dragging = true),
                    onDragExited: (_) => setState(() => dragging = false),
                    onDragDone: _onDrop,
                    child: Stack(children: [
                      Column(children: [
                        ChatHeader(state: s),
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
