// Seeded violations for `npm run lint:selftest` (P14-T04, QG-26.3). Never imported.
type Row = { market_value: string; costBasis: string };

export function unrealised(row: Row): number {
  return Number(row.market_value) - parseFloat(row.costBasis);
}

export function addFee(totalAmount: number, fee: number): number {
  return totalAmount + fee;
}
