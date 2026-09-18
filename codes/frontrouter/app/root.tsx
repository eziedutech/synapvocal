import "@fontsource-variable/inter";
import "@radix-ui/themes/styles.css";
import "./app.css";

import { Theme } from "@radix-ui/themes";
import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useRouteLoaderData,
} from "react-router";

import type { Route } from "./+types/root";
import { AppShell } from "./components/AppShell";
import { Notice } from "./components/Notice";
import type { ShellUser } from "./components/UserMenu";
import { contrib } from "./lib/contrib/contrib.server";
import { getUserId } from "./lib/session.server";

// Who is signed in, for the account menu. Visitors who never signed in cost nothing here.
export async function loader({ request }: Route.LoaderArgs): Promise<{ user: ShellUser | null }> {
  const userId = await getUserId(request);
  if (!userId) return { user: null };
  try {
    const me = await contrib.me(userId);
    return { user: { email: me.email, name: me.name, contributing: Boolean(me.consent) } };
  } catch {
    return { user: null };
  }
}

export const links: Route.LinksFunction = () => [
  { rel: "icon", href: "/favicon.png", type: "image/png", sizes: "128x128" },
  { rel: "apple-touch-icon", href: "/logo-synap.png" },
];

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body>
        <Theme
          appearance="light"
          accentColor="teal"
          grayColor="sage"
          radius="none"
          panelBackground="solid"
        >
          {children}
        </Theme>
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App({ loaderData }: Route.ComponentProps) {
  return (
    <AppShell user={loaderData.user}>
      <Outlet />
    </AppShell>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  let title = "Something went wrong";
  let detail = "An unexpected error occurred.";

  if (isRouteErrorResponse(error)) {
    title = error.status === 404 ? "Page not found" : `Error ${error.status}`;
    detail = error.status === 404 ? "The requested page does not exist." : error.statusText || detail;
  } else if (import.meta.env.DEV && error instanceof Error) {
    detail = error.message;
  }

  const root = useRouteLoaderData<typeof loader>("root");
  return (
    <AppShell user={root?.user ?? null}>
      <Notice tone="error" title={title} detail={detail} />
    </AppShell>
  );
}
