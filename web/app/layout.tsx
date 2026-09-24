import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Shell } from "@/components/Shell";
import { ConfigProvider } from "@/components/ConfigProvider";
import "./globals.css";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Agentic",
  description: "Ten agent modules, live against Claude.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="font-sans antialiased">
        <ConfigProvider>
          <Shell>{children}</Shell>
        </ConfigProvider>
      </body>
    </html>
  );
}
