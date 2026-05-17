import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Indian Law — Plain-language answers with citations",
  description:
    "Ask a question about Indian law. Get a plain-language answer with citations to acts and judgments. Not legal advice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
