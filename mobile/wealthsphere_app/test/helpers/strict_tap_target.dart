import 'dart:ui' as ui;

import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

/// A minimum tap-target guideline without Flutter's "touching a scrollable's edge" exemption.
///
/// Flutter's `androidTapTargetGuideline` skips any node that it considers to be at the boundary of
/// a scrollable; because of how that check compares coordinate spaces, most content inside a
/// scrolling screen is skipped. Screens here scroll, so this version checks every tappable node
/// that is fully on screen (links and hidden nodes excepted, as in Flutter's version).
class StrictTapTargetGuideline extends AccessibilityGuideline {
  const StrictTapTargetGuideline({this.size = const Size(48, 48)});

  final Size size;

  @override
  String get description => 'Every tappable object is at least $size (strict)';

  @override
  Evaluation evaluate(WidgetTester tester) {
    var result = const Evaluation.pass();
    for (final RenderView view in tester.binding.renderViews) {
      result += _traverse(view, view.owner!.semanticsOwner!.rootSemanticsNode!);
    }
    return result;
  }

  Evaluation _traverse(RenderView view, SemanticsNode node) {
    var result = const Evaluation.pass();
    node.visitChildren((child) {
      result += _traverse(view, child);
      return true;
    });
    if (node.isMergedIntoParent) return result;
    final data = node.getSemanticsData();
    final tappable =
        data.hasAction(ui.SemanticsAction.tap) ||
        data.hasAction(ui.SemanticsAction.longPress);
    if (!tappable ||
        data.flagsCollection.isHidden ||
        data.flagsCollection.isLink) {
      return result;
    }
    var bounds = node.rect;
    for (SemanticsNode? n = node; n != null; n = n.parent) {
      if (n.transform != null) {
        bounds = MatrixUtils.transformRect(n.transform!, bounds);
      }
    }
    // The render view's size honours the test surface size; FlutterView.physicalSize does not.
    final dpr = view.configuration.devicePixelRatio;
    final viewRect = Offset.zero & (view.size * dpr);
    // Only judge nodes fully inside the view; partly visible ones cannot be measured.
    if (!viewRect.contains(bounds.topLeft) ||
        !viewRect.contains(bounds.bottomRight - const Offset(1, 1))) {
      return result;
    }
    final logical = bounds.size / dpr;
    if (logical.width < size.width - 0.01 ||
        logical.height < size.height - 0.01) {
      result += Evaluation.fail(
        '"${data.label}" (${data.tooltip}) is ${logical.width.toStringAsFixed(1)}x'
        '${logical.height.toStringAsFixed(1)}, expected at least $size\n',
      );
    }
    return result;
  }
}

const strictTapTargetGuideline = StrictTapTargetGuideline();
