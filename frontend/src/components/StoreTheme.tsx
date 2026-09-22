import type { CSSProperties, ReactNode } from "react";

type StoreThemeProps = {
  primary: string | null;
  secondary: string | null;
  children: ReactNode;
};

/**
 * Paints a shop's own colours over the shared skeleton.
 *
 * Tailwind's utilities read the theme through CSS variables, so overriding the two brand
 * variables on a wrapper repaints everything inside it — buttons, links, borders — without
 * a single class changing. A shop that chose no colours inherits the platform's.
 *
 * Only the primary is given: the secondary follows it, so a hover never jumps from the
 * shop's colour back to the platform blue.
 */
export function StoreTheme({ primary, secondary, children }: StoreThemeProps) {
  if (primary === null && secondary === null) {
    return <>{children}</>;
  }
  const brand = primary ?? secondary;
  const style = {
    ...(brand === null ? {} : { "--color-brand": brand }),
    "--color-brand-dark": secondary ?? brand,
  } as CSSProperties;

  return (
    <div style={style} className="contents">
      {children}
    </div>
  );
}
