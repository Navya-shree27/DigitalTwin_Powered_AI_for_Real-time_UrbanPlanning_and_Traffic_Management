/**
 * frontend/src/utils/timeFormat.js
 * ────────────────────────────────
 * Utility functions for formatting simulation execution timers,
 * dynamic ETA estimations, and completed run durations.
 */

/**
 * Formats elapsed seconds into a digital clock format (MM:SS or HH:MM:SS).
 * @param {number} totalSeconds
 * @returns {string} e.g. "00:24", "02:15", "01:05:30"
 */
export function formatElapsed(totalSeconds) {
  if (totalSeconds == null || isNaN(totalSeconds) || totalSeconds < 0) {
    return '00:00'
  }
  const sec = Math.floor(totalSeconds)
  const hours = Math.floor(sec / 3600)
  const minutes = Math.floor((sec % 3600) / 60)
  const seconds = sec % 60

  const pad = (n) => String(n).padStart(2, '0')

  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
  }
  return `${pad(minutes)}:${pad(seconds)}`
}

/**
 * Formats estimated remaining time into a concise, human-readable ETA string.
 * @param {number|null} etaSeconds
 * @returns {string} e.g. "~24s", "~1m 15s", "~1h 20m", "Finalizing..."
 */
export function formatETA(etaSeconds) {
  if (etaSeconds == null || isNaN(etaSeconds)) {
    return 'Estimating…'
  }
  if (etaSeconds <= 0.5) {
    return 'Finalizing…'
  }

  const sec = Math.round(etaSeconds)
  if (sec < 60) {
    return `~${sec}s`
  }

  const hours = Math.floor(sec / 3600)
  const minutes = Math.floor((sec % 3600) / 60)
  const remainingSec = sec % 60

  if (hours > 0) {
    return `~${hours}h ${minutes}m`
  }
  if (remainingSec > 0) {
    return `~${minutes}m ${remainingSec}s`
  }
  return `~${minutes}m`
}

/**
 * Formats completed total simulation duration.
 * @param {number|null} totalSeconds
 * @returns {string} e.g. "42.8s", "2m 14s", "1h 12m 30s"
 */
export function formatDuration(totalSeconds) {
  if (totalSeconds == null || isNaN(totalSeconds) || totalSeconds <= 0) {
    return '—'
  }
  if (totalSeconds < 60) {
    return `${Number(totalSeconds).toFixed(1)}s`
  }

  const sec = Math.round(totalSeconds)
  const hours = Math.floor(sec / 3600)
  const minutes = Math.floor((sec % 3600) / 60)
  const remainingSec = sec % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m ${remainingSec}s`
  }
  if (remainingSec > 0) {
    return `${minutes}m ${remainingSec}s`
  }
  return `${minutes}m`
}
