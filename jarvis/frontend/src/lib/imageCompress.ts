const MAX_IMAGE_DIM = 1280;
const JPEG_QUALITY = 0.7;

/**
 * Reads an image File, downscales it to fit within `maxDim`, and returns a
 * compressed JPEG data-URL. Keeps embedded photos (damage / driving-license)
 * small enough to store in JSON / a base64 column. Resolves null on any
 * decode/read failure.
 */
export function fileToCompressedDataUrl(
  file: File,
  maxDim: number = MAX_IMAGE_DIM,
  quality: number = JPEG_QUALITY,
): Promise<string | null> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onerror = () => resolve(null);
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => resolve(null);
      img.onload = () => {
        let { width, height } = img;
        if (width > maxDim || height > maxDim) {
          const scale = Math.min(maxDim / width, maxDim / height);
          width = Math.round(width * scale);
          height = Math.round(height * scale);
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(null);
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL('image/jpeg', quality));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}
