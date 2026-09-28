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

/**
 * Same downscale+JPEG compression as fileToCompressedDataUrl, but returns a
 * File (for multipart uploads, e.g. the photo gallery). Falls back to the
 * original file on any decode/read/encode failure so an upload never silently
 * drops an image.
 */
export function fileToCompressedFile(
  file: File,
  maxDim: number = MAX_IMAGE_DIM,
  quality: number = JPEG_QUALITY,
): Promise<File> {
  return new Promise((resolve) => {
    // Only attempt to re-encode raster images; leave anything else untouched.
    if (!file.type.startsWith('image/')) {
      resolve(file)
      return
    }
    const reader = new FileReader()
    reader.onerror = () => resolve(file)
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => resolve(file)
      img.onload = () => {
        let { width, height } = img
        if (width > maxDim || height > maxDim) {
          const scale = Math.min(maxDim / width, maxDim / height)
          width = Math.round(width * scale)
          height = Math.round(height * scale)
        }
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          resolve(file)
          return
        }
        ctx.drawImage(img, 0, 0, width, height)
        canvas.toBlob(
          (blob) => {
            if (!blob) {
              resolve(file)
              return
            }
            const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
            resolve(new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified }))
          },
          'image/jpeg',
          quality,
        )
      }
      img.src = reader.result as string
    }
    reader.readAsDataURL(file)
  })
}
