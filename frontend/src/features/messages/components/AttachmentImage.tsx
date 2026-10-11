import React, { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { api } from '../../../lib/api';
import { Skeleton } from '../../../components/ui/Skeleton';

interface AttachmentImageProps {
  conversationId: string;
  messageId: string;
  alt: string;
}

/**
 * Photo jointe à un message. Jamais d'URL publique : le contenu est lu par
 * un appel authentifié (réservé aux deux participants), puis affiché via
 * une URL locale `blob:` révoquée dès que l'image quitte l'écran.
 */
export const AttachmentImage: React.FC<AttachmentImageProps> = ({
  conversationId,
  messageId,
  alt,
}) => {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let ignore = false;
    let objectUrl: string | null = null;
    api
      .getMessageAttachmentBlob(conversationId, messageId)
      .then((blob) => {
        if (ignore) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!ignore) setFailed(true);
      });
    return () => {
      ignore = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [conversationId, messageId]);

  if (failed) {
    return (
      <span className="flex items-center gap-2 rounded-field bg-surface-muted px-3 py-6 text-sm text-muted-foreground">
        <ImageOff aria-hidden className="w-4 h-4" />
        Image indisponible
      </span>
    );
  }
  if (!url) return <Skeleton className="h-48 w-56 max-w-full" />;
  return (
    <img
      src={url}
      alt={alt}
      className="block max-h-72 w-auto max-w-full rounded-field object-cover"
    />
  );
};
