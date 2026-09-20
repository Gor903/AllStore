const CURRENCY_SIGNS: Record<string, string> = { AMD: "֏", USD: "$", EUR: "€", RUB: "₽" };

/**
 * A price arrives as a decimal string. It is only ever shown, never computed on, and the
 * values are far below the range where a double loses a lepton — so Number is enough here.
 */
export function formatPrice(price: string, currency: string): string {
  const amount = Number(price);
  if (!Number.isFinite(amount)) {
    return `${price} ${currency}`;
  }
  // a round price reads better without the zeroes after the comma
  const fractionDigits = Number.isInteger(amount) ? 0 : 2;
  const formatted = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(amount);
  return `${formatted} ${CURRENCY_SIGNS[currency] ?? currency}`;
}
