import { useCallback, useEffect, useState } from "react";
import { DevPanel } from "./dev/DevPanel";
import { Library } from "./screens/Library";
import { Reader } from "./screens/Reader";

function parseHash(): { bookId: string | null } {
  const m = location.hash.match(/^#\/book\/([\w-]+)/);
  return { bookId: m ? m[1] : null };
}

export function App() {
  const [route, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const open = useCallback((bookId: string) => {
    location.hash = `#/book/${bookId}`;
  }, []);
  const back = useCallback(() => {
    location.hash = "#/";
  }, []);

  return (
    <>
      {route.bookId ? <Reader key={route.bookId} bookId={route.bookId} onBack={back} /> : <Library onOpen={open} />}
      <DevPanel />
    </>
  );
}
