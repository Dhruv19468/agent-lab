import { Link } from "react-router";

import { EmptyState } from "../components/ui";

export function NotFoundPage() {
  return (
    <EmptyState
      title="This page doesn't exist"
      body="The link may be old, or the agent, skill or tool was deleted."
      action={
        <Link to="/" className="font-medium text-ink-900 underline underline-offset-2">
          Go to the overview
        </Link>
      }
    />
  );
}
