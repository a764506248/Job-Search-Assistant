export function isClosedMessageChannel(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /message channel (?:is )?closed|extension port.*back\/forward cache|receiving end does not exist|could not establish connection/i.test(message)
}

export function isMissingMessageReceiver(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /receiving end does not exist|could not establish connection/i.test(message)
}
