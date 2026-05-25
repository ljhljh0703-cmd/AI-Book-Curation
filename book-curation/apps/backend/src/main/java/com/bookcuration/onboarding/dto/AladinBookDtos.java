package com.taeo.bookcuration.onboarding.dto;

import java.util.List;

public final class AladinBookDtos {

    private AladinBookDtos() {
    }

    public record AladinBookSearchResponse(
            int totalResults,
            int startIndex,
            int itemsPerPage,
            String query,
            List<AladinBookItemResponse> items
    ) {
    }

    public record AladinBookItemResponse(
            String aladinItemId,
            String isbn,
            String isbn13,
            String title,
            String author,
            String publisher,
            String pubDate,
            String description,
            String coverUrl,
            String categoryId,
            String categoryName,
            Integer customerReviewRank,
            Integer priceSales,
            Integer priceStandard
    ) {
    }
}
