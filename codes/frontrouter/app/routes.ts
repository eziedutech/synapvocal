import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/bridge.tsx"),
  route("benchmark", "routes/benchmark.tsx"),
  route("contribute", "routes/contribute.tsx"),
  route("contribute/session", "routes/contribute.session.tsx"),
  route("contribute/upload", "routes/contribute.upload.ts"),
  route("contribute/audio/:id", "routes/contribute.audio.ts"),
  route("auth/session", "routes/auth.session.ts"),
  route("health", "routes/health.ts"),
  route("stt/token", "routes/stt.token.ts"),
  route("bridge/interpret", "routes/bridge.interpret.ts"),
  route("tts/speak", "routes/tts.speak.ts"),
] satisfies RouteConfig;
