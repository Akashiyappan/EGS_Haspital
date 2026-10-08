import { Link } from 'react-router';

export default function NotFoundPage() {
  return (
    <div className="full-page-center">
      <div className="card stack">
        <h1>Page not found</h1>
        <p className="muted">The page you are looking for doesn’t exist.</p>
        <Link to="/" className="button">
          Go home
        </Link>
      </div>
    </div>
  );
}
