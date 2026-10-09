import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../tokens/tokens.dart';

/// The message box of the AI chat: a multiline field with a character limit and a send button
/// that becomes a stop button while a reply is streaming.
///
/// - Send is disabled for empty (or whitespace-only) text and while [streaming].
/// - The text is trimmed and the field cleared on send; over-long input is blocked, not truncated
///   silently, by the length limit.
/// - It moves up with the keyboard because it sits inside the screen's `Scaffold` body/`SafeArea`.
class AIChatComposer extends StatefulWidget {
  const AIChatComposer({
    required this.onSend,
    this.onStop,
    this.streaming = false,
    this.enabled = true,
    this.maxLength = 2000,
    super.key,
  });

  final ValueChanged<String> onSend;

  /// Called by the stop button; the button shows only while [streaming].
  final VoidCallback? onStop;
  final bool streaming;

  /// False disables typing and sending (for example while offline).
  final bool enabled;
  final int maxLength;

  @override
  State<AIChatComposer> createState() => _AIChatComposerState();
}

class _AIChatComposerState extends State<AIChatComposer> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _canSend =>
      widget.enabled && !widget.streaming && _controller.text.trim().isNotEmpty;

  void _send() {
    if (!_canSend) return;
    final text = _controller.text.trim();
    _controller.clear();
    widget.onSend(text);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsetsDirectional.all(AppSpacing.s),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                enabled: widget.enabled,
                minLines: 1,
                maxLines: 5,
                maxLength: widget.maxLength,
                maxLengthEnforcement: MaxLengthEnforcement.enforced,
                textInputAction: TextInputAction.newline,
                keyboardType: TextInputType.multiline,
                onChanged: (_) => setState(() {}),
                buildCounter:
                    (
                      context, {
                      required currentLength,
                      required isFocused,
                      maxLength,
                    }) => currentLength > widget.maxLength * 0.8
                    ? Text(
                        l10n.chatCounter(
                          '$currentLength',
                          '${widget.maxLength}',
                        ),
                      )
                    : null,
                decoration: InputDecoration(hintText: l10n.chatHint),
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            if (widget.streaming)
              IconButton.filledTonal(
                tooltip: l10n.chatStop,
                onPressed: widget.onStop,
                icon: const Icon(Icons.stop_rounded),
                constraints: const BoxConstraints.tightFor(
                  width: AppTouchTarget.android,
                  height: AppTouchTarget.android,
                ),
              )
            else
              IconButton.filled(
                tooltip: l10n.chatSend,
                onPressed: _canSend ? _send : null,
                icon: const Icon(Icons.arrow_upward_rounded),
                constraints: const BoxConstraints.tightFor(
                  width: AppTouchTarget.android,
                  height: AppTouchTarget.android,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
