import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  /**
   * 수정 포인트:
   * - Tailwind CSS v4 공식 Vite 플러그인을 추가했다.
   * - shadcn/ui 컴포넌트에서 '@/...' alias를 사용할 수 있도록 resolve.alias를 추가했다.
   */
  const proxyTarget =
    env.VITE_API_PROXY_TARGET ||
    env.VITE_API_BASE_URL ||
    "https://book-api.taeo-dev.com";

  // 수정: og:image/twitter:image의 로고 캐시가 고정되지 않도록 빌드 시점 버전을 주입한다.
  // index.html 안의 %BOOKEMON_ASSET_VERSION% 값이 npm run build 때마다 현재 시간값으로 치환된다.
  const bookemonAssetVersion = Date.now().toString();

  return {
    plugins: [
      react(),
      tailwindcss(),
      {
        name: "bookemon-html-cache-busting",
        transformIndexHtml(html) {
          return html.replaceAll("%BOOKEMON_ASSET_VERSION%", bookemonAssetVersion);
        },
      },
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      proxy:
        env.VITE_USE_RELATIVE_API === "true"
          ? {
              "/api": {
                target: proxyTarget,
                changeOrigin: true,
                secure: true,
              },
              "/oauth2": {
                target: proxyTarget,
                changeOrigin: true,
                secure: true,
                configure: (proxy) => {
    proxy.on("proxyReq", (_proxyReq, req) => {
      console.log("[proxy:/oauth2]", req.method, req.url);
    });
  },
              },
              "/login/oauth2": {
                target: proxyTarget,
                changeOrigin: true,
                secure: true,
              },
            }
          : undefined,
    },
  };
});
