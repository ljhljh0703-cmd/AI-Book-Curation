import { toNativeAbsoluteUrl } from "./mobileRuntime";

/**
 * 이미지 URL 표시용 유틸입니다.
 * DB에는 원본 URL을 그대로 저장하고, 브라우저에서 읽을 때만 cache-buster query string을 붙입니다.
 */

const DAILY_IMAGE_CACHE_VERSION = new Date()
  .toISOString()
  .slice(0, 10)
  .replace(/-/g, "");

export const toCacheBustedImageUrl = (
  imageUrl?: string | null,
  version?: string | number | null
): string => {
  if (!imageUrl) return "";

  // 수정 포인트: 브라우저 로컬 미리보기 URL과 base64 데이터 URL에는 query string을 붙이면 깨질 수 있습니다.
  if (/^(blob:|data:)/i.test(imageUrl)) {
    return imageUrl;
  }

  const displayUrl = toNativeAbsoluteUrl(imageUrl);
  const cacheVersion = String(version ?? DAILY_IMAGE_CACHE_VERSION);
  const separator = displayUrl.includes("?") ? "&" : "?";

  // 수정 포인트: DB 저장값은 건드리지 않고, 화면에서 읽을 때만 v 파라미터를 붙여 브라우저 캐시를 우회합니다.
  return `${displayUrl}${separator}v=${encodeURIComponent(cacheVersion)}`;
};