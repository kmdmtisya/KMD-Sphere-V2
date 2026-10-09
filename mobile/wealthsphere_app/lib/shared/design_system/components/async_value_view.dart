import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'skeleton_loader.dart';
import 'state_views.dart';

/// Renders an [AsyncValue] as a skeleton, an error with Retry, an empty state or the data.
///
/// Rules:
/// - **No value yet and loading** -> skeleton.
/// - **No value and failed** -> [ErrorState] (generic message; the exception is never shown).
/// - **Has a value**, even while refreshing or after a failed refresh -> the data, so users keep
///   seeing the last good figures. Show a `StaleDataBanner` above it when a refresh failed.
/// - A value that [isEmpty] -> [empty].
class AsyncValueView<T> extends StatelessWidget {
  const AsyncValueView({
    required this.value,
    required this.data,
    this.loading,
    this.empty,
    this.isEmpty,
    this.onRetry,
    this.errorBuilder,
    super.key,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final Widget? loading;
  final Widget? empty;
  final bool Function(T data)? isEmpty;
  final VoidCallback? onRetry;
  final Widget Function(Object error, StackTrace stackTrace)? errorBuilder;

  @override
  Widget build(BuildContext context) {
    final current = value;
    if (current.hasValue) {
      final loaded = current.requireValue;
      if (isEmpty?.call(loaded) ?? false) return empty ?? const EmptyState();
      return data(loaded);
    }
    if (current.hasError) {
      return errorBuilder?.call(
            current.error!,
            current.stackTrace ?? StackTrace.empty,
          ) ??
          ErrorState(onRetry: onRetry);
    }
    return loading ?? SkeletonLoader.card();
  }
}
