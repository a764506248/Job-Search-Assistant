const BOSS_PRIVATE_DIGIT_START = 0xE031
const BOSS_PRIVATE_DIGIT_END = 0xE03A

/**
 * BOSS search cards render salary digits with the `kanzhun-mix` font. The
 * current page bundle maps U+E031..U+E03A to 0..9 before inserting the text
 * into the DOM. Decode only that verified range and fail closed if another
 * private-use character appears, because a different font mapping must not be
 * guessed.
 */
export function decodeBossSalaryText(value: string | null | undefined): string | undefined {
  const text = value?.trim()
  if (!text) return undefined

  const decoded: string[] = []
  for (const character of text) {
    const codePoint = character.codePointAt(0)!
    if (codePoint >= BOSS_PRIVATE_DIGIT_START && codePoint <= BOSS_PRIVATE_DIGIT_END) {
      decoded.push(String(codePoint - BOSS_PRIVATE_DIGIT_START))
      continue
    }
    if (isPrivateUseCodePoint(codePoint)) return undefined
    decoded.push(character)
  }
  return decoded.join('')
}

function isPrivateUseCodePoint(codePoint: number): boolean {
  return (codePoint >= 0xE000 && codePoint <= 0xF8FF)
    || (codePoint >= 0xF0000 && codePoint <= 0xFFFFD)
    || (codePoint >= 0x100000 && codePoint <= 0x10FFFD)
}
