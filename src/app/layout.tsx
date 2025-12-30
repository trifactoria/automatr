import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Automatr",
  description: "Host + container automation control portal",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {/* Optional: a subtle app background wrapper */}
        <div style={{ minHeight: "100vh" }}>
          {children}
        </div>
      </body>
    </html>
  );
}

