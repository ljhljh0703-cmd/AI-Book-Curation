import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.taeodev.bookemon",
  appName: "Bookemon",
  webDir: "dist",
  server: {
    url: 'https://book.taeo-dev.com',
    cleartext: false,
  },
};

export default config;
