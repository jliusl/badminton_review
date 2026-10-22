import { useEffect, useState } from "react";
import Dashboard from "./components/Dashboard";
import ProjectEditor from "./components/ProjectEditor";

function projectIdFromHash(): string | null {
  const match = window.location.hash.match(/^#\/project\/([^/?]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export default function App() {
  const [projectId, setProjectId] = useState<string | null>(projectIdFromHash());

  useEffect(() => {
    const onHashChange = () => setProjectId(projectIdFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return projectId ? (
    <ProjectEditor projectId={projectId} />
  ) : (
    <Dashboard onOpen={(id) => (window.location.hash = `/project/${id}`)} />
  );
}