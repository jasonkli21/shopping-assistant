import { useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, Project } from "../../api/client";
import { AssistantPanel } from "./AssistantPanel";

export function ProjectAssistant({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  return (
    <AssistantPanel
      project={project}
      onProjectUpdate={(updated, replayed) => {
        if (replayed) {
          void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
        } else {
          queryClient.setQueryData(["project", project.id], updated);
        }
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ["shortlist", project.id] }),
          queryClient.invalidateQueries({ queryKey: ["rejections", project.id] }),
          queryClient.invalidateQueries({ queryKey: ["project-comparisons", project.id] }),
        ]);
      }}
      onRevisionConflict={async (error) => {
        await queryClient.invalidateQueries({ queryKey: ["project", project.id] });
        if (error instanceof ApiRequestError && error.status !== 409) throw error;
      }}
    />
  );
}
