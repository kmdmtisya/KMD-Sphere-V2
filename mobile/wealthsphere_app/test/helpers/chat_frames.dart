import 'dart:convert';

/// Server-sent event frames as the chat API writes them, for tests.
String frame(String event, Map<String, Object?> data) =>
    'event: $event\ndata: ${jsonEncode(data)}\n\n';

Map<String, Object?> done({
  Map<String, Object?>? structured,
  String conversation = 'c1',
}) => {
  'type': 'done',
  'conversation_id': conversation,
  'message_id': 'm1',
  'model': 'fake-1',
  'provider': 'fake',
  'tool_calls': 1,
  'structured': structured,
};

/// A validated answer: the four sections and the server's own notice.
Map<String, Object?> answer() => {
  'observed': [
    {'text': 'Your net worth was retrieved.', 'source': 'get_net_worth'},
  ],
  'calculated': [
    {'text': 'Assets minus liabilities.', 'source': 'get_net_worth'},
  ],
  'assumptions': ['Values are in USD.'],
  'interpretation': 'A snapshot, not a guarantee.',
  'caveats': ['Forecasts are illustrations, not guaranteed returns.'],
};
