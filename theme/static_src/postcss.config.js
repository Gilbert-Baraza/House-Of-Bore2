/*
 * theme/static_src/postcss.config.js
 * ──────────────────────────────────────────────────────────────────────────────
 * PostCSS plugin configuration for Tailwind CSS v4.
 *
 * WHY ONLY @tailwindcss/postcss:
 *   Tailwind CSS v4 is a complete PostCSS plugin — it handles its own:
 *     - CSS nesting (no postcss-nested needed)
 *     - CSS custom properties / variables (no postcss-simple-vars needed)
 *     - Autoprefixer (built into the @tailwindcss/postcss package)
 *
 *   Adding postcss-nested or postcss-simple-vars alongside v4 can cause
 *   conflicts and is not recommended.
 * ──────────────────────────────────────────────────────────────────────────────
 */

module.exports = {
  plugins: {
    // The official Tailwind CSS v4 PostCSS plugin.
    // Processes @import "tailwindcss", @theme, @source, @layer, and all
    // Tailwind utility class generation in a single pass.
    "@tailwindcss/postcss": {},
  },
};
