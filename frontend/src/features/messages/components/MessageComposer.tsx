import React, { useRef, useState } from 'react';
import { ImagePlus, SendHorizontal } from 'lucide-react';
import { IconButton } from '../../../components/ui/IconButton';
import { cn } from '../../../lib/cn';

interface MessageComposerProps {
  onSend: (text: string) => void;
  onSendImage: (file: File, caption: string) => void;
}

/** Hauteur maximale de la zone de saisie avant défilement interne. */
const MAX_HEIGHT_PX = 128;

/** Clavier physique (ordinateur) : Entrée envoie ; sur mobile, Entrée fait un retour à la ligne. */
function hasFinePointer(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: fine)').matches;
}

/**
 * Saisie d'un message, collée en bas de l'écran. Une photo peut être jointe
 * (JPEG ou PNG) ; le texte déjà tapé lui sert alors de légende. Le serveur
 * reste l'autorité sur les formats et tailles acceptés.
 */
export const MessageComposer: React.FC<MessageComposerProps> = ({ onSend, onSendImage }) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT_PX)}px`;
  };

  const submit = () => {
    if (!text.trim()) return;
    onSend(text);
    setText('');
    requestAnimationFrame(resize);
    textareaRef.current?.focus();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing &&
      hasFinePointer()
    ) {
      event.preventDefault();
      submit();
    }
  };

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Réinitialisé : resélectionner la même photo redéclenche l'envoi.
    event.target.value = '';
    if (!file) return;
    onSendImage(file, text);
    setText('');
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="flex items-end gap-2"
    >
      <label
        className={cn(
          'inline-flex shrink-0 w-11 h-11 items-center justify-center rounded-full text-primary-emerald cursor-pointer',
          'hover:bg-emerald-tint focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary-emerald',
        )}
      >
        <ImagePlus aria-hidden className="w-6 h-6" />
        <input
          type="file"
          accept="image/jpeg,image/png"
          aria-label="Joindre une photo"
          className="sr-only"
          onChange={handleFile}
        />
      </label>
      <label htmlFor="message-saisie" className="sr-only">
        Votre message
      </label>
      <textarea
        id="message-saisie"
        ref={textareaRef}
        rows={1}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          resize();
        }}
        onKeyDown={handleKeyDown}
        placeholder="Écrire un message…"
        className="min-h-11 flex-1 resize-none rounded-field bg-surface px-4 py-2.5 text-base text-foreground placeholder:text-muted-foreground-soft ring-1 ring-inset ring-muted-foreground-soft focus:outline-none focus:ring-2 focus:ring-primary-emerald"
      />
      <IconButton label="Envoyer" type="submit" tone="brand" disabled={!text.trim()}>
        <SendHorizontal aria-hidden className="w-5 h-5" />
      </IconButton>
    </form>
  );
};
