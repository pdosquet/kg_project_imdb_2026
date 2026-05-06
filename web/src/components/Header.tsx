import { APP_TITLE, SPARQL_ENDPOINT } from "../config";

interface RootOption {
  iri: string;
  label: string;
}

interface Props {
  roots: RootOption[];
  activeRoot: string;
  onChangeRoot: (iri: string) => void;
}

export function Header({ roots, activeRoot, onChangeRoot }: Props) {
  return (
    <header className="header">
      <div className="header-title">{APP_TITLE}</div>
      <div className="header-root-nav">
        <span className="header-label">Browsing:</span>
        {roots.map((r) => (
          <button
            key={r.iri}
            className={`root-btn ${r.iri === activeRoot ? "active" : ""}`}
            onClick={() => onChangeRoot(r.iri)}
          >
            {r.label}
          </button>
        ))}
      </div>
      <div className="header-endpoint">{SPARQL_ENDPOINT}</div>
    </header>
  );
}
