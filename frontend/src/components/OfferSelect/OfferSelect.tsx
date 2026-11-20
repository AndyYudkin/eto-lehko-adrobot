import { useCallback, useEffect, useRef } from 'react';
import type { StylesConfig } from 'react-select';
import AsyncSelect from 'react-select/async';

import { searchOffers, type OfferOption } from '../../api';

const DEBOUNCE_MS = 300;

const selectStyles: StylesConfig<OfferOption, false> = {
  control: (base, state) => ({
    ...base,
    minHeight: 'var(--control-height)',
    borderRadius: 'var(--radius-control)',
    borderColor: state.isFocused
      ? 'var(--color-accent)'
      : 'var(--color-input-border)',
    boxShadow: 'none',
    '&:hover': { borderColor: 'var(--color-accent)' },
  }),
  menu: (base) => ({
    ...base,
    borderRadius: 'var(--radius-control)',
    border: '1px solid var(--color-border)',
    overflow: 'hidden',
  }),
  // the menu is portalled to <body> (see below), so it must sit above
  // dialogs and cards; nothing else in the app sets a z-index this high
  menuPortal: (base) => ({ ...base, zIndex: 1000 }),
  option: (base, state) => ({
    ...base,
    color: 'var(--color-text)',
    backgroundColor: state.isSelected
      ? 'var(--color-chip-bg)'
      : state.isFocused
        ? 'var(--color-panel-bg)'
        : 'var(--color-surface)',
  }),
  singleValue: (base) => ({ ...base, color: 'var(--color-text)' }),
  placeholder: (base) => ({ ...base, color: 'var(--color-muted)' }),
  noOptionsMessage: (base) => ({ ...base, color: 'var(--color-muted)' }),
  input: (base) => ({ ...base, color: 'var(--color-text)' }),
};

function formatLabel(o: OfferOption) {
  return `#${o.id} ${o.name}`;
}

type OfferSelectProps = {
  value: OfferOption | null;
  onChange: (value: OfferOption | null) => void;
  inputId: string;
  excludeStreamId?: string;
};

export function OfferSelect({
  value,
  onChange,
  inputId,
  excludeStreamId,
}: OfferSelectProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancelPrev = useRef<(() => void) | undefined>(undefined);

  // debounce: each new call resolves the previous one empty and waits
  const loadOptions = useCallback(
    (input: string) =>
      new Promise<OfferOption[]>((resolve, reject) => {
        clearTimeout(timer.current);
        cancelPrev.current?.();
        cancelPrev.current = () => resolve([]);
        timer.current = setTimeout(() => {
          cancelPrev.current = undefined;
          searchOffers(input, excludeStreamId).then(resolve, reject);
        }, DEBOUNCE_MS);
      }),
    [excludeStreamId],
  );

  useEffect(() => () => clearTimeout(timer.current), []);

  return (
    <AsyncSelect<OfferOption, false>
      inputId={inputId}
      placeholder="Search offer by ID or name"
      value={value}
      onChange={onChange}
      loadOptions={loadOptions}
      getOptionValue={(o) => String(o.id)}
      getOptionLabel={formatLabel}
      noOptionsMessage={({ inputValue }) =>
        inputValue.trim() ? 'No offers' : 'Type to search'
      }
      styles={selectStyles}
      // render the menu in <body>: stream cards clip their content
      // (overflow: hidden), which cut the dropdown off
      menuPortalTarget={document.body}
      menuPosition="fixed"
      menuPlacement="auto"
    />
  );
}
