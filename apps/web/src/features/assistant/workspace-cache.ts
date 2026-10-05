import { QueryClient } from "@tanstack/react-query";

export function invalidateProjectWorkspace(
  queryClient: QueryClient,
  projectId: string,
  { invalidateProject = true }: { invalidateProject?: boolean } = {},
) {
  return Promise.all([
    ...(invalidateProject ? [queryClient.invalidateQueries({ queryKey: ["project", projectId] })] : []),
    queryClient.invalidateQueries({ queryKey: ["project-products", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["shortlist", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["rejections", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["decision", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["user-note", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["comparison", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["product-research", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] }),
  ]);
}
