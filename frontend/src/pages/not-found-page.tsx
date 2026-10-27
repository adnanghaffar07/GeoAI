import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <section>
      <h1 className="text-[1.75rem] font-semibold tracking-tight">Page not found</h1>
      <p className="mt-2 text-asphalt-500">This page does not exist. The link may be wrong or out of date.</p>
      <Link to="/" className="mt-4 inline-block text-sm link">
        Go to the home page
      </Link>
    </section>
  )
}
