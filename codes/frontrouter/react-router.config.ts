import type { Config } from "@react-router/dev/config";

export default {
  ssr: true,
  // Dokploy's Traefik ends TLS, so the server sees http:// while the browser's Origin
  // header says https://. React Router's CSRF check compares both and refused every
  // form action in production. The public domain is allowed by name; any other origin
  // is still refused.
  allowedActionOrigins: ["synap.eziedutech.dev"],
} satisfies Config;
