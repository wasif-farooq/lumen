import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import '../chat/chat_view.dart';
import '../preview/file_details.dart';

/// Phone: the chat with the paired laptop, chats in the drawer, results open in a sheet.
class MobileChat extends StatefulWidget {
  const MobileChat({super.key, required this.state, required this.onUnpair});
  final AppState state;
  final VoidCallback onUnpair;

  @override
  State<MobileChat> createState() => _MobileChatState();
}

class _MobileChatState extends State<MobileChat> {
  AppState get s => widget.state;

  Future<void> _open(Hit hit, {double start = 0}) async {
    try {
      final msg = await s.api.open(hit.path, start: start);
      _toast(msg.startsWith('NOT OPENED') ? 'Test mode: nothing was opened.' : 'Opened on ${s.host}${start > 0 ? ' at ${clock(start)}' : ''}');
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _show(Hit hit) async {
    try {
      await s.api.show(hit.path);
      _toast('Folder opened on ${s.host}');
    } catch (e) {
      _toast('$e');
    }
  }

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  void _sheet(Hit hit) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
        child: FileDetails(
          api: s.api,
          hit: hit,
          mobile: true,
          onOpen: (h, {double start = 0}) {
            Navigator.pop(context);
            _open(h, start: start);
          },
          onShow: () {
            Navigator.pop(context);
            _show(hit);
          },
          onAsk: (q) {
            Navigator.pop(context);
            s.send(q);
          },
          onSimilar: () {
            Navigator.pop(context);
            s.findSimilar(path: hit.path);
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: s,
        builder: (context, _) {
          final title = s.chats.where((c) => c.id == s.chatId).firstOrNull?.title ?? 'New chat';
          return Scaffold(
            appBar: AppBar(
              backgroundColor: C.bg,
              surfaceTintColor: Colors.transparent,
              titleSpacing: 0,
              title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                Row(children: [
                  StatusDot(size: 7, color: s.connectError == null ? C.green : C.red),
                  const SizedBox(width: 6),
                  Text('${s.host} · ${s.connectError == null ? 'connected' : 'offline'}', style: const TextStyle(fontSize: 12, color: C.text3)),
                ]),
              ]),
              actions: [IconButton(tooltip: 'New chat', onPressed: s.newChat, icon: const Icon(Icons.add))],
              bottom: const PreferredSize(preferredSize: Size.fromHeight(1), child: Divider(height: 1)),
            ),
            drawer: Drawer(
              backgroundColor: C.panel,
              child: SafeArea(
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  const Padding(
                    padding: EdgeInsets.all(20),
                    child: Row(children: [Logo(), SizedBox(width: 10), Text('Chats', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16))]),
                  ),
                  Expanded(
                    child: ListView(children: [
                      for (final c in s.chats)
                        ListTile(
                          title: Text(c.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                          selected: c.id == s.chatId,
                          selectedColor: C.text,
                          selectedTileColor: C.raised,
                          onTap: () {
                            Navigator.pop(context);
                            s.openChat(c.id);
                          },
                        ),
                    ]),
                  ),
                  ListTile(leading: const Icon(Icons.link_off), title: Text('Unpair from ${s.host}'), onTap: widget.onUnpair),
                ]),
              ),
            ),
            body: Column(children: [
              Expanded(child: ChatView(state: s, compact: true, onOpen: _open, onShow: _show, onHitTap: _sheet)),
              SafeArea(top: false, child: Composer(state: s, compact: true)),
            ]),
          );
        },
      );
}
