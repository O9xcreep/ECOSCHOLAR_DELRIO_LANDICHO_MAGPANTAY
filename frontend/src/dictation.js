// Browser speech-to-text support (Web Speech API). Chrome/Edge expose it as
// webkitSpeechRecognition; browsers without it (e.g. Firefox) get null here.
export const SpeechRecognition =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition || null
    : null

export const isDictationSupported = Boolean(SpeechRecognition)

// Adds dictated text to whatever is already in the field instead of replacing it.
export function appendDictation(current, text) {
  const base = (current || '').trimEnd()
  return base ? `${base} ${text}` : text
}
