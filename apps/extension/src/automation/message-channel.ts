export function isClosedMessageChannel(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /message channel closed|receiving end does not exist|could not establish connection/i.test(message)
}

export function isMissingMessageReceiver(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /receiving end does not exist|could not establish connection/i.test(message)
}
