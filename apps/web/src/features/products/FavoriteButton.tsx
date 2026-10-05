import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, catalogApi } from "../../api/client";

export function FavoriteButton({ variantId }: { variantId: string }) {
  const queryClient = useQueryClient();
  const stateKey = ["favorite", variantId] as const;
  const favoriteQuery = useQuery({
    queryKey: stateKey,
    queryFn: ({ signal }) => catalogApi.favoriteState(variantId, signal),
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: () => {
      const current = favoriteQuery.data;
      const version = current?.version ?? 0;
      return current?.favorite
        ? catalogApi.unfavorite(variantId, version)
        : catalogApi.favorite(variantId, version);
    },
    onSuccess: async (value) => {
      queryClient.setQueryData(stateKey, value);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["saved-products"] }),
        queryClient.invalidateQueries({ queryKey: ["favorite"] }),
      ]);
    },
    onError: async (error) => {
      if (error instanceof ApiRequestError && error.status === 409) {
        await favoriteQuery.refetch();
      }
    },
  });

  if (favoriteQuery.isPending) return <p role="status">Loading saved-product state…</p>;
  if (favoriteQuery.isError) {
    return <p className="field-error" role="alert">Favorite state could not load.</p>;
  }
  return (
    <div className="favorite-control">
      <button
        className={`button ${favoriteQuery.data.favorite ? "secondary-button" : "quiet-button"}`}
        type="button"
        disabled={mutation.isPending}
        aria-pressed={favoriteQuery.data.favorite}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending
          ? "Saving…"
          : favoriteQuery.data.favorite
            ? "Remove from Saved Products"
            : "Save to favorites"}
      </button>
      {mutation.isError && <p className="field-error" role="alert">{mutation.error.message || "Favorite could not be saved."}</p>}
    </div>
  );
}
