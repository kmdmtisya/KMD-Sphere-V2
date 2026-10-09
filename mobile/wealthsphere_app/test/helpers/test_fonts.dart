import 'dart:io';

import 'package:flutter/services.dart';

/// Loads real fonts (Roboto and the Material icon font) from the Flutter SDK so that golden
/// images show readable text and icons instead of the default test font's solid blocks.
///
/// The fonts come from the SDK that runs the tests (pinned in CI), so nothing is committed and
/// rendering is identical wherever that Flutter version is used. Golden images are only
/// authoritative on the CI Linux runner (see dart_test.yaml).
Future<void> loadTestFonts() async {
  final dir = Directory('${_flutterRoot()}/bin/cache/artifacts/material_fonts');
  if (!dir.existsSync()) {
    throw StateError('Material fonts not found at ${dir.path}');
  }

  final roboto = FontLoader('Roboto');
  for (final file in dir.listSync().whereType<File>()) {
    final name = file.uri.pathSegments.last.toLowerCase();
    if (name.startsWith('roboto') && name.endsWith('.ttf')) {
      roboto.addFont(
        Future.value(ByteData.sublistView(file.readAsBytesSync())),
      );
    }
  }
  await roboto.load();

  final icons = File('${dir.path}/MaterialIcons-Regular.otf');
  final iconFile = icons.existsSync()
      ? icons
      : File('${dir.path}/materialicons-regular.otf');
  final materialIcons = FontLoader('MaterialIcons')
    ..addFont(Future.value(ByteData.sublistView(iconFile.readAsBytesSync())));
  await materialIcons.load();
}

String _flutterRoot() {
  final fromEnv = Platform.environment['FLUTTER_ROOT'];
  if (fromEnv != null && fromEnv.isNotEmpty) return fromEnv;
  // flutter_tester lives under <root>/bin/cache/artifacts/engine/...
  var dir = File(Platform.resolvedExecutable).parent;
  while (dir.parent.path != dir.path) {
    if (Directory('${dir.path}/bin/cache/artifacts/material_fonts')
        .existsSync()) {
      return dir.path;
    }
    dir = dir.parent;
  }
  throw StateError('Could not locate the Flutter SDK root; set FLUTTER_ROOT');
}
