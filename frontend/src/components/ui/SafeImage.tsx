import React, { useState } from 'react';

interface SafeImageProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  src?: string | null;
  fallback: string;
}

/**
 * Image tolérante aux pannes : URL absente ou cassée -> image de repli
 * locale, jamais une icône d'image brisée.
 *
 * Chargement différé par défaut (`loading="lazy"`, décodage asynchrone) :
 * sur mobile et réseau lent, seules les images proches de l'écran sont
 * téléchargées. Une image visible dès l'arrivée (héros) peut repasser en
 * `loading="eager"` explicitement.
 */
export const SafeImage: React.FC<SafeImageProps> = ({
  src,
  fallback,
  onError,
  loading = 'lazy',
  decoding = 'async',
  ...props
}) => {
  const [hasError, setHasError] = useState(false);
  const [lastSrc, setLastSrc] = useState(src);

  // Nouvelle URL : on retente le chargement (ajustement d'état pendant le
  // rendu, pattern React officiel, plutôt qu'un useEffect).
  if (src !== lastSrc) {
    setLastSrc(src);
    setHasError(false);
  }

  return (
    <img
      {...props}
      loading={loading}
      decoding={decoding}
      src={hasError || !src ? fallback : src}
      onError={(event) => {
        setHasError(true);
        onError?.(event);
      }}
    />
  );
};
