package com.taeo.bookcuration.onboarding.service;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.taeo.bookcuration.config.AladinProperties;
import com.taeo.bookcuration.onboarding.dto.AladinBookDtos.AladinBookItemResponse;
import com.taeo.bookcuration.onboarding.dto.AladinBookDtos.AladinBookSearchResponse;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Objects;

@Service
public class AladinBookSearchService {

    private final AladinProperties aladinProperties;
    private final RestClient restClient;

    public AladinBookSearchService(AladinProperties aladinProperties, RestClient.Builder restClientBuilder) {
        this.aladinProperties = aladinProperties;
        this.restClient = restClientBuilder.baseUrl(aladinProperties.baseUrl()).build();
    }

    public AladinBookSearchResponse search(String keyword, Integer limit, Integer start) {
        String query = normalizeKeyword(keyword);
        int safeLimit = aladinProperties.clampLimit(limit == null ? 0 : limit);
        int safeStart = start == null || start <= 0 ? 1 : start;

        if (!aladinProperties.hasTtbKey()) {
            throw new IllegalStateException("알라딘 TTBKey가 설정되어 있지 않습니다. ALADIN_TTB_KEY 환경변수를 확인해 주세요.");
        }

        AladinApiResponse response = restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/ttb/api/ItemSearch.aspx")
                        .queryParam("TTBKey", aladinProperties.safeTtbKey())
                        .queryParam("Query", query)
                        .queryParam("QueryType", "Keyword")
                        .queryParam("MaxResults", safeLimit)
                        .queryParam("start", safeStart)
                        .queryParam("SearchTarget", aladinProperties.searchTarget())
                        .queryParam("Output", aladinProperties.output())
                        .queryParam("Version", aladinProperties.version())
                        // 수정 포인트: 알라딘 응답 링크에 TTBKey가 노출되지 않도록 API 요청 단계에서 제외 옵션을 함께 전달합니다.
                        .queryParam("Omitkey", 1)
                        .build())
                .retrieve()
                .body(AladinApiResponse.class);

        if (response == null) {
            return new AladinBookSearchResponse(0, safeStart, safeLimit, query, List.of());
        }

        List<AladinBookItemResponse> items = safeItems(response.item()).stream()
                .filter(Objects::nonNull)
                .map(this::toResponse)
                .toList();

        return new AladinBookSearchResponse(
                nullToZero(response.totalResults()),
                defaultValue(response.startIndex(), safeStart),
                defaultValue(response.itemsPerPage(), safeLimit),
                response.query() == null ? query : response.query(),
                items
        );
    }

    private AladinBookItemResponse toResponse(AladinApiItem item) {
        return new AladinBookItemResponse(
                item.itemId(),
                normalizeBlank(item.isbn()),
                normalizeBlank(item.isbn13()),
                normalizeBlank(item.title()),
                normalizeBlank(item.author()),
                normalizeBlank(item.publisher()),
                normalizeBlank(item.pubDate()),
                stripHtml(normalizeBlank(item.description())),
                normalizeUrl(item.cover()),
                normalizeBlank(item.categoryId()),
                normalizeBlank(item.categoryName()),
                item.customerReviewRank(),
                item.priceSales(),
                item.priceStandard()
        );
    }

    private static String normalizeKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("도서 검색어를 입력해 주세요.");
        }
        String trimmed = keyword.trim();
        if (trimmed.length() < 2) {
            throw new IllegalArgumentException("도서 검색어는 최소 2글자 이상 입력해 주세요.");
        }
        return trimmed;
    }

    private static List<AladinApiItem> safeItems(List<AladinApiItem> items) {
        return items == null ? List.of() : items;
    }

    private static int nullToZero(Integer value) {
        return value == null ? 0 : value;
    }

    private static int defaultValue(Integer value, int defaultValue) {
        return value == null ? defaultValue : value;
    }

    private static String normalizeBlank(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static String normalizeUrl(String value) {
        String normalized = normalizeBlank(value);
        if (normalized == null) {
            return null;
        }
        // 수정 포인트: 샘플 복사 과정에서 들어간 "https: //" 같은 공백 URL도 화면 표시 전에 보정합니다.
        return normalized
                .replace("https: //", "https://")
                .replace("http: //", "http://");
    }

    private static String stripHtml(String value) {
        if (value == null) {
            return null;
        }

        String unescaped = value
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&amp;", "&")
                .replace("&quot;", "\"")
                .replace("&#39;", "'");

        return unescaped.replaceAll("<[^>]*>", " ")
                .replaceAll("\\s+", " ")
                .trim();
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record AladinApiResponse(
            Integer totalResults,
            Integer startIndex,
            Integer itemsPerPage,
            String query,
            List<AladinApiItem> item
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record AladinApiItem(
            String itemId,
            String title,
            String link,
            String author,
            String pubDate,
            String description,
            String isbn,
            String isbn13,
            Integer priceSales,
            Integer priceStandard,
            String cover,
            String categoryId,
            String categoryName,
            String publisher,
            Integer customerReviewRank
    ) {
    }
}
