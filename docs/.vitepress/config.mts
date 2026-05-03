import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  title: 'IR2MQTT',
  description: 'The Ultimate IR Gateway',
  base: '/ir2mqtt/',
  mermaid: {},
  vite: {
    ssr: {
      noExternal: ['vitepress-plugin-mermaid', 'mermaid'],
    },
    optimizeDeps: {
      include: ['mermaid'],
    },
  },
  themeConfig: {
    nav: [
      { text: 'Guide', link: '/devices' },
      { text: 'Developer', link: '/dev-setup' },
    ],
    sidebar: [
      {
        text: 'Setup Guide',
        items: [
          { text: 'Hardware Setup & Installation', link: '/hardware-setup' },
          { text: 'ir2mqtt_bridge Component', link: '/bridge-component' },
        ],
      },
      {
        text: 'Getting Started',
        items: [
          { text: 'Devices', link: '/devices' },
          { text: 'Buttons & Codes', link: '/buttons-codes' },
          { text: 'Automations', link: '/automations' },
          { text: 'IR Database', link: '/ir-database' },
          { text: 'Bridges', link: '/bridges' },
          { text: 'Settings', link: '/settings' },
          { text: 'Troubleshooting', link: '/troubleshooting' },
        ],
      },
      {
        text: 'Integration',
        items: [
          { text: 'MQTT Topic Reference', link: '/mqtt' },
          { text: 'WebSocket API', link: '/websocket' },
        ],
      },
      {
        text: 'Developer',
        items: [
          { text: 'Local Setup & Architecture', link: '/dev-setup' },
          { text: 'Testing & CI/CD', link: '/dev-testing' },
          { text: 'REST API', link: '/dev-api' },
          { text: 'Database Migrations', link: '/dev-migrations' },
        ],
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/steelcuts/ir2mqtt' },
    ],
  },
}))
