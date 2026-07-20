import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Everything inlines into one index.html: the Python CLI ships that file as a
// template and injects run data, so pip users never need Node.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
});
