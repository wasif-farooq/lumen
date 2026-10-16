import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../theme.dart';

const _imageTypes = XTypeGroup(label: 'Images', extensions: ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff', 'heic']);

/// A photo to search with: a file picker on desktop; camera or gallery on the phone.
Future<Uint8List?> pickPhoto(BuildContext context) async {
  if (Platform.isLinux || Platform.isMacOS || Platform.isWindows) {
    final file = await openFile(acceptedTypeGroups: [_imageTypes], confirmButtonText: 'Search with this photo');
    return file?.readAsBytes();
  }
  final source = await showModalBottomSheet<ImageSource>(
    context: context,
    builder: (_) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Padding(padding: EdgeInsets.only(bottom: 8), child: Text('Search with a photo', style: TextStyle(fontWeight: FontWeight.w600))),
        ListTile(leading: const Icon(Icons.photo_camera_outlined, color: C.accent), title: const Text('Take a photo'), onTap: () => Navigator.pop(context, ImageSource.camera)),
        ListTile(leading: const Icon(Icons.photo_library_outlined, color: C.accent), title: const Text('Choose from gallery'), onTap: () => Navigator.pop(context, ImageSource.gallery)),
      ]),
    ),
  );
  if (source == null) return null;
  final photo = await ImagePicker().pickImage(source: source, maxWidth: 1600, imageQuality: 90);
  return photo?.readAsBytes();
}
