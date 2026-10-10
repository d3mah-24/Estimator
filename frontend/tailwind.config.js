import frappeUIPreset from 'frappe-ui/tailwind'

export default {
  presets: [frappeUIPreset],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    './node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}',
    // INFO: uncomment the line below if you have workspaces set up
    // '../node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // Equans Bid accent (teal) and the app frame (navy). Status colours stay frappe-ui's.
      colors: {
        brand: {
          50: '#effcf8',
          100: '#d4f6ec',
          200: '#a9ecd9',
          300: '#71dbc1',
          400: '#38c1a5',
          500: '#16a38b',
          600: '#0c8372',
          700: '#0d695d',
          800: '#0f544b',
          900: '#10453f',
        },
        navy: {
          700: '#1f3354',
          800: '#152642',
          900: '#0d1a30',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(13, 26, 48, 0.06), 0 1px 3px rgba(13, 26, 48, 0.04)',
      },
    },
  },
  plugins: []
}
