export function isCurrentRequest(
  requestId: number,
  activeRequestId: number,
  signal: AbortSignal,
): boolean {
  return requestId === activeRequestId && !signal.aborted;
}
