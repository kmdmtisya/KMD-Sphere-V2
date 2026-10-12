import 'api_exception.dart';

/// Why a load failed, in the few categories the UI treats differently.
enum LoadFailure {
  /// The device cannot reach the service: show the offline state and keep last-good data.
  offline,

  /// The session ended: send the user to sign in; retrying cannot help.
  signedOut,
  forbidden,
  notFound,

  /// Too many requests or a server fault: temporary, retry later.
  busy,

  /// Anything else, including malformed responses and demo-data errors.
  unknown;

  /// Whether a Retry button makes sense.
  bool get retryable => this != signedOut && this != forbidden;
}

/// Classifies any error a repository can throw.
LoadFailure loadFailureOf(Object? error) {
  if (error is! ApiException) return LoadFailure.unknown;
  return switch (error.kind) {
    ApiErrorKind.network => LoadFailure.offline,
    ApiErrorKind.unauthenticated => LoadFailure.signedOut,
    ApiErrorKind.forbidden => LoadFailure.forbidden,
    ApiErrorKind.notFound => LoadFailure.notFound,
    ApiErrorKind.rateLimited || ApiErrorKind.server => LoadFailure.busy,
    ApiErrorKind.validation ||
    ApiErrorKind.invalidResponse ||
    ApiErrorKind.unexpected => LoadFailure.unknown,
  };
}

/// The support reference of a failure, if the API sent one.
String? supportReferenceOf(Object? error) =>
    error is ApiException ? error.correlationId : null;
