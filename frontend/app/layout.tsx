import type { Metadata, Viewport } from "next";
import { Public_Sans } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const body = Public_Sans({ variable: "--ff-body", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "FoodFlow",
  description:
    "Move surplus food to local organizations with less coordination. Post what is available, track pickup, and keep a record of every confirmed donation.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

// Apply a saved light/dark choice before first paint (the default follows the device).
const THEME_SCRIPT = `try{var t=localStorage.getItem("foodflow_theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={body.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
