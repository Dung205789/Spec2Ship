import "./globals.css";

export const metadata = {
  title: "Spec2Ship — AI Code Pipeline",
  description: "Upload your codebase, describe what needs fixing or building — the AI pipeline handles the rest.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <div className="app-shell">
          <nav className="topbar">
            <a href="/" className="topbar-brand">
              <div className="logo">⚡</div>
              Spec2Ship
              <span className="topbar-badge">AI PIPELINE</span>
            </a>
            <div className="topbar-nav">
              <a href="/">Dashboard</a>
              <a href="/runs">All Runs</a>
            </div>
          </nav>
          <main className="main-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
