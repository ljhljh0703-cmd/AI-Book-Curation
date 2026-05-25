export interface LibrarySyncResponse {
  totalCount: number;
  savedCount: number;
  pageCount: number;
}

export interface LibrarySyncConfigResponse {
  configured: boolean;
  baseUrl: string;
  pageSize: number;
}
