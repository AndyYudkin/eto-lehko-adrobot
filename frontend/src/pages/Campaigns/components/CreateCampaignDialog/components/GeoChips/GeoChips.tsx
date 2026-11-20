import {
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type KeyboardEvent,
} from 'react';

import styles from './GeoChips.module.css';

const GEO_RE = /^[A-Z]{2}$/;

type GeoChipsProps = {
  value: string[];
  onChange: (value: string[]) => void;
};

export function GeoChips({ value, onChange }: GeoChipsProps) {
  const [text, setText] = useState('');
  const [hint, setHint] = useState('');

  // adds valid codes from `raw` (separated by commas/whitespace) to the list
  function commit(raw: string) {
    const parts = raw
      .split(/[\s,]+/)
      .map((p) => p.trim().toUpperCase())
      .filter(Boolean);
    const next = [...value];
    const rejected: string[] = [];
    for (const part of parts) {
      if (!GEO_RE.test(part)) rejected.push(part);
      else if (!next.includes(part)) next.push(part);
    }
    if (next.length !== value.length) onChange(next);
    setHint(rejected.length ? 'Use 2-letter codes, e.g. MX' : '');
    setText(rejected.join(', '));
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (text.trim()) commit(text);
    } else if (e.key === 'Backspace' && text === '' && value.length > 0) {
      onChange(value.slice(0, -1));
      setHint('');
    }
  }

  function handlePaste(e: ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    commit(`${text},${e.clipboardData.getData('text')}`);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    setText(e.target.value);
    setHint('');
  }

  return (
    <div>
      <div className={styles.box}>
        {value.map((geo) => (
          <span key={geo} className={styles.chip}>
            {geo}
            <button
              type="button"
              className={styles.remove}
              aria-label={`Remove ${geo}`}
              onClick={() => onChange(value.filter((g) => g !== geo))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          id="geo"
          className={styles.input}
          placeholder="Add code"
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
        />
      </div>
      {hint && <p className={styles.hint}>{hint}</p>}
    </div>
  );
}
