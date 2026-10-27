/**
 * Position of an AI box as percentages of the photo, so it lines up with the picture at any
 * display size (the preview is smaller than the original the box was measured on).
 */
export function boxStyle(bbox: readonly [number, number, number, number], width: number, height: number) {
  const [left, top, right, bottom] = bbox
  const percent = (value: number) => `${Math.round(value * 100000) / 1000}%`
  return {
    left: percent(left / width),
    top: percent(top / height),
    width: percent((right - left) / width),
    height: percent((bottom - top) / height),
  }
}
