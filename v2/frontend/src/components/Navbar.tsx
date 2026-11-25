import React from "react";

interface NavbarProps {
  visible: boolean;
}

const NAV_LINKS = ["Services", "About Us", "Projects", "Team", "Contacts"];

export const Navbar: React.FC<NavbarProps> = ({ visible }) => {
  if (!visible) return null;

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between pl-3 pr-8 lg:pl-3 lg:pr-16 py-5 animate-fade-in">
      {/* Logo */}
      <a href="#" className="text-[hsl(var(--foreground))] text-xl font-semibold tracking-tight">
        SENTINEL AI
      </a>

      {/* Center nav links */}
      <div className="hidden md:flex items-center gap-8">
        {NAV_LINKS.map((link) => (
          <a
            key={link}
            href={`#${link.toLowerCase().replace(/\s+/g, "-")}`}
            className="text-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors uppercase tracking-widest"
          >
            {link}
          </a>
        ))}
      </div>

      {/* CTA */}
      <button className="hidden md:inline-flex items-center rounded-lg uppercase text-xs tracking-widest px-6 py-2.5 text-[hsl(var(--foreground))] bg-[hsl(var(--nav-button))] hover:bg-[hsl(var(--nav-button))]/80 active:scale-[0.97] transition-all">
        Get Quote
      </button>
    </nav>
  );
};
