import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, JetBrains_Mono, Public_Sans } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const display = Bricolage_Grotesque({ variable: "--ff-display", subsets: ["latin"], display: "swap" });
const body = Public_Sans({ variable: "--ff-body", subsets: ["latin"], display: "swap" });
const data = JetBrains_Mono({ variable: "--ff-data", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "FoodFlow",
  description: "Good Food. Greater Impact. Real time food rescue: surplus restaurant food to community organizations.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#1456d9" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${data.variable}`}>
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
