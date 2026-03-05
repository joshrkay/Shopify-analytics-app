import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from '../ui/command';
import { globalSearch } from '../../services/searchApi';
import type { SearchResult } from '../../services/searchApi';

interface GlobalSearchProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GlobalSearch({ open, onOpenChange }: GlobalSearchProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keyboard shortcut: Cmd+K / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onOpenChange]);

  const performSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const response = await globalSearch(q);
      setResults(response.results);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Clear pending debounce on unmount to prevent state updates on unmounted component
  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  const handleInputChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => performSearch(value), 300);
  };

  const handleSelect = (path: string) => {
    navigate(path);
    onOpenChange(false);
    setQuery('');
    setResults([]);
  };

  // Group results by type
  const pages = results.filter(r => r.type === 'page');
  const dashboards = results.filter(r => r.type === 'dashboard');

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder="Search pages, dashboards..."
        value={query}
        onValueChange={handleInputChange}
      />
      <CommandList>
        {loading && <CommandEmpty>Searching...</CommandEmpty>}
        {!loading && query.length >= 2 && results.length === 0 && (
          <CommandEmpty>No results found.</CommandEmpty>
        )}
        {pages.length > 0 && (
          <CommandGroup heading="Pages">
            {pages.map(r => (
              <CommandItem key={r.path} onSelect={() => handleSelect(r.path)}>
                {r.title}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {dashboards.length > 0 && (
          <CommandGroup heading="Dashboards">
            {dashboards.map(r => (
              <CommandItem key={r.path} onSelect={() => handleSelect(r.path)}>
                {r.title}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
