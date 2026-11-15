/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional override for where raw-hotspot packs are served from. */
  readonly VITE_HOTSPOT_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
