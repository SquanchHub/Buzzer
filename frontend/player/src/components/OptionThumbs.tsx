import { ImageThumb } from './ImageThumb';
import { optionImageId, optionLetter } from '../lib/options';

/**
 * Small thumbnails, each with its letter, for the options at `indices` that have an image
 * (T8 D8: the player's choice and the correct choice on results and game over). Options
 * without an image are skipped; renders nothing if none of them has one.
 */
export function OptionThumbs({
  indices,
  imageIds,
  size = 'h-12 w-16',
}: {
  indices: number[];
  imageIds: (number | null)[] | undefined;
  size?: string;
}) {
  const shown = indices.filter((i) => optionImageId(imageIds, i) !== null);
  if (shown.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {shown.map((i) => (
        <span key={i} className="inline-flex items-center gap-1">
          <span className="text-xs font-bold text-ink-muted">{optionLetter(i)}</span>
          <ImageThumb imageId={optionImageId(imageIds, i)!} alt={`Option ${optionLetter(i)}`} className={size} />
        </span>
      ))}
    </span>
  );
}
