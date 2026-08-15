import React, { useState, useRef, useEffect } from 'react'
import './ScenarioDropdown.css'

export default function ScenarioDropdown({
  scenarios = [],
  activeScenarioId,
  onSelectScenario,
  onDeleteScenario
}) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef(null)

  const activeScenario = scenarios.find(s => s.id === activeScenarioId)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleDelete = (e, scenario) => {
    e.stopPropagation()
    if (window.confirm(`Are you sure you want to delete scenario "${scenario.name}"?`)) {
      if (onDeleteScenario) {
        onDeleteScenario(scenario.id)
      }
    }
  }

  return (
    <div className="scenario-dropdown-container" ref={containerRef}>
      <button
        type="button"
        className={`scenario-dropdown-trigger ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title="Select Traffic Scenario"
      >
        <span className="scenario-dropdown-name">
          {activeScenario ? activeScenario.name : 'Select scenario…'}
        </span>
        <span className="scenario-dropdown-chevron">▼</span>
      </button>

      {isOpen && (
        <div className="scenario-dropdown-menu">
          {scenarios.length === 0 ? (
            <div className="scenario-dropdown-empty">No scenarios available</div>
          ) : (
            scenarios.map(s => {
              const isActive = s.id === activeScenarioId
              return (
                <div
                  key={s.id}
                  className={`scenario-dropdown-item ${isActive ? 'active' : ''}`}
                  onClick={() => {
                    onSelectScenario(s.id)
                    setIsOpen(false)
                  }}
                >
                  <div className="scenario-item-label">
                    {isActive && <span className="scenario-item-check">✓</span>}
                    <span className="scenario-item-text">{s.name}</span>
                  </div>
                  <button
                    type="button"
                    className="scenario-delete-btn"
                    onClick={(e) => handleDelete(e, s)}
                    title={`Delete scenario ${s.name}`}
                  >
                    🗑️
                  </button>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
