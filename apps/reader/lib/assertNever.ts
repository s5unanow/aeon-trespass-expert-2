/**
 * Exhaustive type checking helper for discriminated unions.
 */
export function assertNever(value: never): never {
  throw new Error(`Unexpected value: ${JSON.stringify(value)}`);
}
