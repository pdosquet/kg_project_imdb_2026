import { useEffect, useState } from "react";

interface Props {
  value: string;
  onChange: (q: string) => void;
}

export function SearchBar({ value, onChange }: Props) {
  const [local, setLocal] = useState(value);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  useEffect(() => {
    if (local === value) return;
    const t = setTimeout(() => onChange(local), 250);
    return () => clearTimeout(t);
  }, [local, value, onChange]);

  return (
    <input
      type="search"
      className="search-bar"
      placeholder="Search by name or title…"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
    />
  );
}
