import React from 'react'

/**
 * FormattedNarrative
 * Parses raw AI/engine markdown and renders a polished, executive-ready diagnostic UI
 * without any raw special characters (###, **, *, etc.) bleeding through.
 */
export default function FormattedNarrative({ text, onSelectNode, onInspectSignalPlan }) {
  if (!text) return null

  // Normalize and split lines
  const lines = text.split('\n')

  const parseInlineFormatting = (lineText) => {
    // Replace **bold** with <strong>
    const parts = []
    let remaining = lineText

    // Regex to match **bold**, `code`, and Node numbers
    const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`|Node\s+\d+)/g
    let match
    let lastIndex = 0

    while ((match = tokenRegex.exec(lineText)) !== null) {
      const matchStart = match.index
      const matchEnd = tokenRegex.lastIndex
      const matchedStr = match[0]

      // Push preceding plain text
      if (matchStart > lastIndex) {
        parts.push(lineText.substring(lastIndex, matchStart))
      }

      if (matchedStr.startsWith('**') && matchedStr.endsWith('**')) {
        const inner = matchedStr.slice(2, -2)
        parts.push(
          <strong key={matchStart} style={{ color: '#f8fafc', fontWeight: 600 }}>
            {inner}
          </strong>
        )
      } else if (matchedStr.startsWith('`') && matchedStr.endsWith('`')) {
        const code = matchedStr.slice(1, -1)
        parts.push(
          <code
            key={matchStart}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              padding: '1px 5px',
              borderRadius: 4,
              fontSize: '0.9em',
              fontFamily: 'monospace',
              color: '#38bdf8',
            }}
          >
            {code}
          </code>
        )
      } else if (matchedStr.startsWith('Node ')) {
        const nodeId = matchedStr.replace('Node ', '').trim()
        parts.push(
          <button
            key={matchStart}
            type="button"
            onClick={() => onSelectNode && onSelectNode(nodeId)}
            title={`Inspect Node ${nodeId}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 3,
              background: 'rgba(56, 189, 248, 0.15)',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              color: '#38bdf8',
              borderRadius: 4,
              padding: '1px 6px',
              fontSize: '0.9em',
              fontWeight: 600,
              cursor: onSelectNode ? 'pointer' : 'default',
              margin: '0 2px',
              verticalAlign: 'baseline',
            }}
          >
            📍 Node {nodeId}
          </button>
        )
      }

      lastIndex = matchEnd
    }

    if (lastIndex < lineText.length) {
      parts.push(lineText.substring(lastIndex))
    }

    return parts.length > 0 ? parts : lineText
  }

  const renderContent = () => {
    const elements = []
    let inList = false
    let currentList = []

    const flushList = (key) => {
      if (currentList.length > 0) {
        elements.push(
          <ul
            key={key}
            style={{
              margin: '4px 0 8px 0',
              paddingLeft: 18,
              listStyleType: 'none',
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            {currentList}
          </ul>
        )
        currentList = []
        inList = false
      }
    }

    lines.forEach((line, index) => {
      const trimmed = line.trim()
      if (!trimmed) {
        flushList(`list-flush-${index}`)
        return
      }

      // ── 1. Heading (### or ##) ──────────────────────────────────────────
      if (trimmed.startsWith('###') || trimmed.startsWith('##')) {
        flushList(`list-before-h-${index}`)
        const headingText = trimmed.replace(/^#{2,4}\s*/, '')
        elements.push(
          <div
            key={`h-${index}`}
            style={{
              fontSize: 12.5,
              fontWeight: 700,
              color: '#60a5fa',
              letterSpacing: '0.2px',
              marginTop: elements.length > 0 ? 12 : 2,
              marginBottom: 6,
              paddingBottom: 4,
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {headingText}
          </div>
        )
        return
      }

      // ── 2. Health & Efficiency Banner ────────────────────────────────────
      if (
        trimmed.includes('Network Overall Health:') ||
        trimmed.includes('Network Health:')
      ) {
        flushList(`list-before-health-${index}`)
        // Clean out raw stars
        const cleanLine = trimmed.replace(/\*\*/g, '')
        const isExcellent =
          cleanLine.includes('EXCELLENT') || cleanLine.includes('GOOD')
        const isModerate = cleanLine.includes('MODERATE')

        const badgeColor = isExcellent
          ? '#22c55e'
          : isModerate
          ? '#f59e0b'
          : '#ef4444'
        const badgeBg = isExcellent
          ? 'rgba(34, 197, 94, 0.12)'
          : isModerate
          ? 'rgba(245, 158, 11, 0.12)'
          : 'rgba(239, 68, 68, 0.12)'
        const badgeBorder = isExcellent
          ? 'rgba(34, 197, 94, 0.3)'
          : isModerate
          ? 'rgba(245, 158, 11, 0.3)'
          : 'rgba(239, 68, 68, 0.3)'

        elements.push(
          <div
            key={`health-${index}`}
            style={{
              background: badgeBg,
              border: `1px solid ${badgeBorder}`,
              borderRadius: 8,
              padding: '8px 12px',
              margin: '6px 0 10px 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: badgeColor,
                  boxShadow: `0 0 8px ${badgeColor}`,
                }}
              />
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  color: badgeColor,
                  letterSpacing: '0.4px',
                }}
              >
                {cleanLine}
              </span>
            </div>
            {onInspectSignalPlan && (
              <button
                type="button"
                onClick={onInspectSignalPlan}
                style={{
                  fontSize: 10,
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: 'rgba(255, 255, 255, 0.1)',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  color: '#e2e8f0',
                  cursor: 'pointer',
                }}
              >
                Inspect Signals ›
              </button>
            )}
          </div>
        )
        return
      }

      // ── 3. Bullet points (• or - or *) ──────────────────────────────────
      if (
        trimmed.startsWith('•') ||
        trimmed.startsWith('- ') ||
        (trimmed.startsWith('* ') && !trimmed.startsWith('**'))
      ) {
        inList = true
        const itemText = trimmed.replace(/^[•\-\*]\s*/, '')
        currentList.push(
          <li
            key={`li-${index}`}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 6,
              fontSize: 11.5,
              lineHeight: 1.55,
              color: 'var(--text-secondary, #cbd5e1)',
            }}
          >
            <span
              style={{
                color: '#38bdf8',
                fontWeight: 700,
                marginTop: 1,
                fontSize: 12,
              }}
            >
              •
            </span>
            <div style={{ flex: 1 }}>{parseInlineFormatting(itemText)}</div>
          </li>
        )
        return
      }

      // ── 4. Ordered list (1., 2., etc.) ──────────────────────────────────
      const orderedMatch = trimmed.match(/^(\d+)\.\s+(.*)/)
      if (orderedMatch) {
        flushList(`list-before-ol-${index}`)
        const num = orderedMatch[1]
        const textContent = orderedMatch[2]
        elements.push(
          <div
            key={`ol-${index}`}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              margin: '4px 0',
              fontSize: 11.5,
              lineHeight: 1.5,
              color: 'var(--text-secondary, #cbd5e1)',
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                color: '#94a3b8',
                background: 'rgba(255, 255, 255, 0.08)',
                borderRadius: '50%',
                width: 18,
                height: 18,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                marginTop: 1,
              }}
            >
              {num}
            </span>
            <div style={{ flex: 1 }}>{parseInlineFormatting(textContent)}</div>
          </div>
        )
        return
      }

      // ── 5. Footnote / Disclaimer (*(...)*) ──────────────────────────────
      if (trimmed.startsWith('*(') && trimmed.endsWith(')*')) {
        flushList(`list-before-foot-${index}`)
        const cleanFoot = trimmed.slice(2, -2)
        elements.push(
          <div
            key={`foot-${index}`}
            style={{
              marginTop: 10,
              paddingTop: 6,
              borderTop: '1px dashed rgba(255, 255, 255, 0.08)',
              fontSize: 10,
              fontStyle: 'italic',
              color: 'var(--text-muted, #94a3b8)',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            <span>🛡️</span>
            <span>{cleanFoot}</span>
          </div>
        )
        return
      }

      // ── 6. Category Subheaders (e.g. **➕ Recommended New Signals...**) ───
      if (trimmed.startsWith('**') && trimmed.endsWith('**')) {
        flushList(`list-before-subhead-${index}`)
        const subhead = trimmed.slice(2, -2)
        elements.push(
          <div
            key={`subhead-${index}`}
            style={{
              fontSize: 11.5,
              fontWeight: 700,
              color: '#e2e8f0',
              marginTop: 8,
              marginBottom: 4,
            }}
          >
            {subhead}
          </div>
        )
        return
      }

      // ── 7. Normal paragraph ──────────────────────────────────────────────
      flushList(`list-before-p-${index}`)
      elements.push(
        <p
          key={`p-${index}`}
          style={{
            margin: '4px 0',
            fontSize: 11.5,
            lineHeight: 1.55,
            color: 'var(--text-secondary, #cbd5e1)',
          }}
        >
          {parseInlineFormatting(trimmed)}
        </p>
      )
    })

    flushList('list-end')
    return elements
  }

  return (
    <div
      className="formatted-narrative-container"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {renderContent()}
    </div>
  )
}
