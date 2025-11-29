'use client'

import React, { useState, useRef, useEffect } from 'react'

interface MultiSelectProps {
  options: string[]
  selected: string[]
  onChange: (selected: string[]) => void
  label?: string
  placeholder?: string
}

export const MultiSelect: React.FC<MultiSelectProps> = ({
  options,
  selected,
  onChange,
  label = 'Select options',
  placeholder = 'Select...',
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleToggle = (option: string) => {
    if (selected.includes(option)) {
      onChange(selected.filter((s) => s !== option))
    } else {
      onChange([...selected, option])
    }
  }

  const handleRemove = (option: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onChange(selected.filter((s) => s !== option))
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value)
    setIsOpen(true)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault()
      const trimmedValue = inputValue.trim().toLowerCase()
      
      // Add custom keyword if not already selected
      if (!selected.map(s => s.toLowerCase()).includes(trimmedValue)) {
        onChange([...selected, trimmedValue])
      }
      
      setInputValue('')
      setIsOpen(false)
    } else if (e.key === 'Escape') {
      setIsOpen(false)
      setInputValue('')
    }
  }

  // Filter options based on input
  const filteredOptions = options.filter(option =>
    option.toLowerCase().includes(inputValue.toLowerCase())
  )

  return (
    <div className="space-y-2 relative" ref={dropdownRef}>
      {label && (
        <label className="block text-sm font-medium text-gray-700">{label}</label>
      )}
      
      {/* Input field with selected tags */}
      <div className="relative w-full bg-white border border-gray-300 rounded-md shadow-sm focus-within:ring-1 focus-within:ring-primary-500 focus-within:border-primary-500">
        <div className="flex flex-wrap gap-2 p-2 min-h-[42px]">
          {selected.map((item) => (
            <span
              key={item}
              className="inline-flex items-center px-2 py-1 rounded text-sm font-medium bg-primary-100 text-primary-800"
            >
              <span className="capitalize">{item}</span>
              <button
                onClick={(e) => handleRemove(item, e)}
                className="ml-1 inline-flex items-center p-0.5 rounded-full hover:bg-primary-200"
              >
                <svg
                  className="h-3 w-3"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </span>
          ))}
          
          {/* Input for typing */}
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsOpen(true)}
            placeholder={selected.length === 0 ? placeholder : ''}
            className="flex-1 min-w-[120px] outline-none text-sm"
          />
        </div>
        
        {/* Dropdown arrow */}
        <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
          <svg
            className={`h-5 w-5 text-gray-400 transition-transform ${
              isOpen ? 'transform rotate-180' : ''
            }`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      </div>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute z-10 mt-1 w-full bg-white shadow-lg max-h-60 rounded-md py-1 text-base ring-1 ring-black ring-opacity-5 overflow-auto focus:outline-none sm:text-sm">
          {inputValue.trim() && (
            <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-200">
              Press <kbd className="px-1 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">Enter</kbd> to add "{inputValue.trim()}"
            </div>
          )}
          
          {filteredOptions.length > 0 ? (
            filteredOptions.map((option) => (
              <div
                key={option}
                onClick={() => handleToggle(option)}
                className={`cursor-pointer select-none relative py-2 pl-3 pr-9 hover:bg-primary-50 ${
                  selected.includes(option) ? 'bg-primary-50' : ''
                }`}
              >
                <div className="flex items-center">
                  <span className={`block truncate capitalize ${
                    selected.includes(option) ? 'font-semibold' : 'font-normal'
                  }`}>
                    {option}
                  </span>
                </div>

                {selected.includes(option) && (
                  <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-primary-600">
                    <svg
                      className="h-5 w-5"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </span>
                )}
              </div>
            ))
          ) : inputValue.trim() ? (
            <div className="px-3 py-2 text-sm text-gray-500">
              No matching options. Press Enter to add as custom keyword.
            </div>
          ) : (
            <div className="px-3 py-2 text-sm text-gray-500">
              Type to search or add custom keywords...
            </div>
          )}
        </div>
      )}
    </div>
  )
}

