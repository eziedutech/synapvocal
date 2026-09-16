import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [reactRouter()],
  define: {
    // Baked into the client bundle so a deploy can be proven by searching for it.
    __APP_SHA__: JSON.stringify(process.env.GIT_SHA ?? "dev"),
  },
  resolve: {
    tsconfigPaths: true,
  },
});
