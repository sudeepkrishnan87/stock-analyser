import { useEffect } from "react";

const BASE_ICON_SRC = "/favicon.svg";
const ICON_SIZE = 64;

let baseImagePromise: Promise<HTMLImageElement> | null = null;

function loadBaseImage(): Promise<HTMLImageElement> {
  if (!baseImagePromise) {
    baseImagePromise = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = BASE_ICON_SRC;
    });
  }
  return baseImagePromise;
}

function setFaviconHref(href: string) {
  let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  link.href = href;
}

/** Draws a small badge with `count` onto the base favicon and updates the tab title. */
export function useFaviconBadge(count: number, baseTitle: string) {
  useEffect(() => {
    document.title = count > 0 ? `(${count > 9 ? "9+" : count}) ${baseTitle}` : baseTitle;

    let cancelled = false;
    loadBaseImage()
      .then((img) => {
        if (cancelled) return;
        const canvas = document.createElement("canvas");
        canvas.width = ICON_SIZE;
        canvas.height = ICON_SIZE;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        ctx.drawImage(img, 0, 0, ICON_SIZE, ICON_SIZE);

        if (count > 0) {
          const r = 18;
          const cx = ICON_SIZE - r + 6;
          const cy = r - 6;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.fillStyle = "#ef4444";
          ctx.fill();
          ctx.lineWidth = 3;
          ctx.strokeStyle = "#0a0f1e";
          ctx.stroke();

          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 22px system-ui, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(count > 9 ? "9+" : String(count), cx, cy + 1);
        }

        setFaviconHref(canvas.toDataURL("image/png"));
      })
      .catch(() => {
        // Base icon failed to load — leave the static favicon.svg link alone.
      });

    return () => {
      cancelled = true;
    };
  }, [count, baseTitle]);
}
