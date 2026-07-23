import React, { useState } from 'react';

interface SafeImageProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  src?: string | null;
  fallback: string;
}

export const SafeImage: React.FC<SafeImageProps> = ({ src, fallback, onError, ...props }) => {
  const [hasError, setHasError] = useState(false);
  const [lastSrc, setLastSrc] = useState(src);

  if (src !== lastSrc) {
    setLastSrc(src);
    setHasError(false);
  }

  return (
    <img
      {...props}
      src={hasError || !src ? fallback : src}
      onError={(event) => {
        setHasError(true);
        onError?.(event);
      }}
    />
  );
};
