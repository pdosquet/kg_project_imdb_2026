import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 8080,
    allowedHosts: ["cw-browser.pdosquet.com"],
    proxy: {
      "/sparql": {
        target: "http://localhost:3030",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sparql/, "/culturalworks/sparql"),
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 8080,
    allowedHosts: ["cw-browser.pdosquet.com"],
    proxy: {
      "/sparql": {
        target: "http://localhost:3030",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sparql/, "/culturalworks/sparql"),
      },
    },
  },
});
