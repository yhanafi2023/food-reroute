import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const display = Inter({ variable: "--ff-display", subsets: ["latin"], display: "swap" });
const body = Inter({ variable: "--ff-body", subsets: ["latin"], display: "swap" });
const data = JetBrains_Mono({ variable: "--ff-data", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "FoodFlow",
  description:
    "Move surplus food to local organizations with less coordination. Post what is available, track pickup, and keep a record of every confirmed donation.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#07111f" };

// The dark console is the default look. Apply a saved light choice before first paint.
const THEME_SCRIPT = `try{var t=localStorage.getItem("foodflow_theme");if(t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${data.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
