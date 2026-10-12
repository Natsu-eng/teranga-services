import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { TextField } from '../../../components/ui/Field';

interface SearchBarProps {
  label: string;
  placeholder?: string;
  initialValue?: string;
  onSearch: (value: string) => void;
}

/**
 * Recherche envoyée à la validation (Entrée ou bouton), pas à chaque
 * frappe : une requête par intention, et le texte est cherché littéralement
 * côté serveur (« % » et « _ » ne sont jamais des jokers).
 */
export const SearchBar: React.FC<SearchBarProps> = ({
  label,
  placeholder,
  initialValue = '',
  onSearch,
}) => {
  const [value, setValue] = useState(initialValue);
  return (
    <form
      role="search"
      className="flex items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(value.trim());
      }}
    >
      <TextField
        label={label}
        hideLabel
        placeholder={placeholder}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        maxLength={100}
        className="flex-1"
      />
      <Button
        type="submit"
        variant="outline"
        leadingIcon={<Search aria-hidden className="w-4 h-4" />}
      >
        Rechercher
      </Button>
    </form>
  );
};
