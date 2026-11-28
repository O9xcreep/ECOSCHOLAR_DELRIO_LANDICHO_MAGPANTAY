import { useEffect, useRef, useState } from 'react'
import './MicButton.css'
import { SpeechRecognition, isDictationSupported } from '../dictation'

// Voice dictation via the browser's built-in Web Speech API (no model training,
// no API key, no backend changes). Supported in Chrome and Edge; in browsers
// without it (e.g. Firefox) the button simply isn't rendered, so typing still works.
//
// Privacy: the browser sends the audio to its speech service (Google, in Chrome)
// to transcribe it. We never record or store audio ourselves. The transcript only
// fills the text field, so the user can review and edit it before submitting.
const ERROR_MESSAGES = {
  'not-allowed': 'Microphone access was blocked. Allow it in your browser settings.',
  'service-not-allowed': 'Microphone access was blocked. Allow it in your browser settings.',
  'audio-capture': 'No microphone was found.',
  'no-speech': "Didn't catch that. Try again.",
  network: 'Voice input needs an internet connection.',
}

export default function MicButton({ onText, lang = 'en-PH', label = 'this field', disabled = false }) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const recognitionRef = useRef(null)

  // Stop listening if the component goes away mid-dictation (e.g. modal closed).
  useEffect(() => () => recognitionRef.current?.abort(), [])

  if (!SpeechRecognition) return null

  function toggle() {
    if (listening) {
      recognitionRef.current?.stop()
      return
    }
    setError('')
    const recognition = new SpeechRecognition()
    recognition.lang = lang
    recognition.interimResults = false
    recognition.continuous = false
    recognition.maxAlternatives = 1

    recognition.onresult = event => {
      const text = Array.from(event.results)
        .map(r => r[0].transcript)
        .join(' ')
        .trim()
      if (text) onText(text)
    }
    recognition.onerror = event => {
      if (event.error !== 'aborted') {
        setError(ERROR_MESSAGES[event.error] || 'Voice input failed. Please type instead.')
      }
    }
    recognition.onend = () => {
      setListening(false)
      recognitionRef.current = null
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
      setListening(true)
    } catch {
      setError('Voice input failed. Please type instead.')
    }
  }

  const actionLabel = listening ? `Stop voice input for ${label}` : `Speak to fill in ${label}`

  return (
    <>
      <button
        type="button"
        className={`mic-button ${listening ? 'listening' : ''}`}
        onClick={toggle}
        disabled={disabled}
        aria-label={actionLabel}
        aria-pressed={listening}
        title={`${actionLabel}. Your speech is transcribed by your browser's speech service and is not stored.`}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path
            fill="currentColor"
            d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"
          />
        </svg>
      </button>
      {listening && <span className="mic-status" role="status">Listening…</span>}
      {error && <span className="mic-error" role="alert">{error}</span>}
    </>
  )
}

// Wraps a single input or textarea and overlays the mic button inside it.
export function DictationField({ children, onText, label, lang, multiline = false }) {
  return (
    <div className={`dictation-field ${multiline ? 'multiline' : ''} ${isDictationSupported ? 'has-mic' : ''}`}>
      {children}
      <MicButton onText={onText} label={label} lang={lang} />
    </div>
  )
}
