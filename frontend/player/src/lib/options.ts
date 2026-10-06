/**
 * Option text and images for display (docs/plans/t8-image-support.md D5, D8).
 *
 * `config.optionImageIds` (multiple_choice / multi_select) lists an image ID or null per
 * option. An option with empty text and an image is image-only: wherever option text is
 * shown it reads "(image)", next to its letter.
 *
 * Identical copies in host/src/lib/options.ts and player/src/lib/options.ts (the apps share
 * no code) — keep them in sync.
 */

export function optionLetter(i: number): string {
  return String.fromCharCode(65 + i); // A, B, C, …
}

/** The option's image ID, or null (no image, a null entry, or no optionImageIds at all). */
export function optionImageId(imageIds: (number | null)[] | undefined, i: number): number | null {
  const id = imageIds?.[i];
  return typeof id === 'number' ? id : null;
}

/** The option's text, or "(image)" for an image-only option. */
export function optionText(
  options: string[] | undefined,
  imageIds: (number | null)[] | undefined,
  i: number,
): string {
  const text = options?.[i] ?? '';
  return text.trim() === '' && optionImageId(imageIds, i) !== null ? '(image)' : text;
}

export function hasOptionImages(imageIds: (number | null)[] | undefined): boolean {
  return (imageIds ?? []).some((id) => typeof id === 'number');
}
