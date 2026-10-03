import { describe, expect, it } from 'vitest'
import { decodeBossSalaryText } from './salary'

describe('decodeBossSalaryText', () => {
  it('decodes the verified BOSS private-use digit range', () => {
    expect(decodeBossSalaryText('\uE031\uE032\uE033\uE034\uE035\uE036\uE037\uE038\uE039\uE03A'))
      .toBe('0123456789')
  })

  it('decodes salary ranges while preserving normal punctuation and units', () => {
    expect(decodeBossSalaryText('\uE033\uE036-\uE036\uE031K\u00B7\uE032\uE037薪'))
      .toBe('25-50K·16薪')
    expect(decodeBossSalaryText('\uE037\uE031-\uE032\uE036\uE031元/时'))
      .toBe('60-150元/时')
  })

  it('leaves already-readable salary text unchanged', () => {
    expect(decodeBossSalaryText(' 20-40K·14薪 ')).toBe('20-40K·14薪')
    expect(decodeBossSalaryText('面议')).toBe('面议')
  })

  it('fails closed instead of guessing an unknown private-use glyph', () => {
    expect(decodeBossSalaryText('\uE033\uE041-\uE036\uE031K')).toBeUndefined()
    expect(decodeBossSalaryText('\u{F0001}20K')).toBeUndefined()
  })
})
