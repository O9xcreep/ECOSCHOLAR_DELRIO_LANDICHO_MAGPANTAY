// Max dimension (px) and JPEG quality applied to any image before it's
// previewed or uploaded. A phone camera photo can be 20-50+ MB once
// decoded into memory, which is enough to crash a low-RAM Android device
// mid-upload (surfaces as the OS's own "Unable to complete previous
// operation due to low memory" toast, not an error from this app).
// Downscaling before we ever touch the pixels avoids that, and incidentally
// keeps well under the server's 5MB upload limit.
const MAX_DIMENSION = 1600
const JPEG_QUALITY = 0.8
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024

// Resizes/re-encodes an image file client-side; non-image files (PDFs) pass
// through untouched since canvas can't help there. Falls back to the
// original file on any failure - a failed compression should never block a
// student from submitting their application.
export async function compressImageFile(file) {
  if (!file || !file.type.startsWith('image/')) return file

  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height))
    const width = Math.round(bitmap.width * scale)
    const height = Math.round(bitmap.height * scale)

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height)
    bitmap.close?.()

    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
    if (!blob) return file

    const newName = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return new File([blob], newName, { type: 'image/jpeg', lastModified: Date.now() })
  } catch {
    return file
  }
}
