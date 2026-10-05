import { useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, Project } from "../../api/client";
import { AssistantPanel } from "./AssistantPanel";
import { invalidateProjectWorkspace } from "./workspace-cache";

export function ProjectAssistant({
  project,
  selectedProjectProductIds,
  comparisonId,
}: {
  project: Project;
  selectedProjectProductIds?: string[];
  comparisonId?: string;
}) {
  const queryClient = useQueryClient();
  return (
    <AssistantPanel
      project={project}
      selectedProjectProductIds={selectedProjectProductIds}
      comparisonId={comparisonId}
      onProjectUpdate={(updated, replayed) => {
        if (replayed) {
          void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
        } else {
          queryClient.setQueryData(["project", project.id], updated);
        }
        void invalidateProjectWorkspace(queryClient, project.id, { invalidateProject: replayed });
      }}
      onRevisionConflict={async (error) => {
        await invalidateProjectWorkspace(queryClient, project.id);
        if (error instanceof ApiRequestError && error.status !== 409) throw error;
      }}
    />
  );
}
