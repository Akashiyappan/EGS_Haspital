import { isRouteErrorResponse, Link, useRouteError } from 'react-router';

/** Rendered by the router when a route throws or a lazy chunk fails to load. */
export function RouteError() {
  const error = useRouteError();

  if (import.meta.env.DEV) {
    console.error(error);
  }

  const title = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : 'Unexpected error';

  return (
    <div className="full-page-center">
      <div className="card stack">
        <h1>{title}</h1>
        <p className="muted">Something went wrong while loading this page.</p>
        <div className="row">
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
          <Link to="/" className="button secondary">
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}
