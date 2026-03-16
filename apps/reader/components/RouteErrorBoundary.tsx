/**
 * RouteErrorBoundary — error boundary for route-level errors.
 */

"use client";

interface RouteErrorBoundaryProps {
  error: Error;
  reset: () => void;
}

export function RouteErrorBoundary({ error, reset }: RouteErrorBoundaryProps) {
  return (
    <div className="error-boundary" role="alert">
      <h2>Something went wrong</h2>
      <p>{error.message}</p>
      <button onClick={reset} type="button">
        Try again
      </button>
    </div>
  );
}
