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

// Search boxes replace their text instead of appending, and drop any trailing
// punctuation the speech service adds ("Juan dela Cruz." -> "Juan dela Cruz").
export function dictationToSearch(text) {
  return text.trim().replace(/[.?!,]+$/, '')
}
