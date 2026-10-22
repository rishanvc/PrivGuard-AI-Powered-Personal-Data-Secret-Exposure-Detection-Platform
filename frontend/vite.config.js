import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Pinned so the Django CORS allow-list has a stable origin to trust.
    port: 5173,
    strictPort: true,
  },
})
