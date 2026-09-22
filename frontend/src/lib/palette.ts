export type Swatch = {
  name: string;
  /** Null on the first entry: the shop inherits the platform's look. */
  primary: string | null;
  secondary: string | null;
};

/**
 * Coordinated pairs rather than a free colour picker.
 *
 * Every primary here is dark enough to carry white text, which is what the shared skeleton
 * puts on `bg-brand`. A free picker would let a seller choose pale yellow and end up with
 * unreadable buttons in their own shop — and they would have no way to tell why.
 *
 * The backend accepts any valid `#rrggbb`: which colours are tasteful is a product
 * decision that changes often, and adding a pair here should not need a deploy of the API.
 */
export const PALETTE: readonly Swatch[] = [
  { name: "Как на площадке", primary: null, secondary: null },
  { name: "Синий", primary: "#2f6fed", secondary: "#1e4fb8" },
  { name: "Глина", primary: "#a85832", secondary: "#7d3f22" },
  { name: "Лес", primary: "#2f6b4f", secondary: "#1f4a37" },
  { name: "Слива", primary: "#7b3f72", secondary: "#5a2c53" },
  { name: "Графит", primary: "#37404f", secondary: "#232a35" },
  { name: "Вишня", primary: "#a32f3f", secondary: "#7a222e" },
];

export function swatchOf(primary: string | null, secondary: string | null): Swatch {
  return (
    PALETTE.find((swatch) => swatch.primary === primary && swatch.secondary === secondary) ??
      // a pair set through the API before this screen existed, or by a later palette change
      { name: "Свой цвет", primary, secondary }
  );
}
