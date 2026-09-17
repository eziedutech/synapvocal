import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/bridge.tsx"),
  route("status", "routes/status.tsx"),
  route("health", "routes/health.ts"),
  route("stt/token", "routes/stt.token.ts"),
  route("bridge/interpret", "routes/bridge.interpret.ts"),
  route("tts/speak", "routes/tts.speak.ts"),
] satisfies RouteConfig;
