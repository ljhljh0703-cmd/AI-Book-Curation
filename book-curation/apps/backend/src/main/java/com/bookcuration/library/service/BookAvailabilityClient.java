package com.taeo.bookcuration.library.service;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.taeo.bookcuration.config.Data4LibraryProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
@RequiredArgsConstructor
public class BookAvailabilityClient {

    private final Data4LibraryProperties properties;

    public AvailabilityResult check(String libCode, String isbn13) {
        if (!properties.hasAuthKey()) {
            return AvailabilityResult.failed("DATA4LIBRARY_AUTH_KEY가 설정되어 있지 않습니다.");
        }

        try {
            String baseUrl = properties.baseUrl() == null || properties.baseUrl().isBlank()
                    ? "http://data4library.kr"
                    : properties.baseUrl();

            BookExistResponse response = RestClient.create(baseUrl)
                    .get()
                    .uri(uriBuilder -> uriBuilder
                            .path("/api/bookExist")
                            .queryParam("authKey", properties.authKey())
                            .queryParam("libCode", libCode)
                            .queryParam("isbn13", isbn13)
                            .queryParam("format", "json")
                            .build())
                    .retrieve()
                    .body(BookExistResponse.class);

            BookExistResult result = response == null || response.response() == null
                    ? null
                    : response.response().result();

            if (result == null) {
                return AvailabilityResult.failed("도서관 API 응답에 조회 결과가 없습니다.");
            }

            return new AvailabilityResult(
                    toBoolean(result.hasBook()),
                    toBoolean(result.loanAvailable()),
                    "조회 완료",
                    true
            );
        } catch (Exception ex) {
            return AvailabilityResult.failed("도서관 API 조회에 실패했습니다: " + ex.getMessage());
        }
    }

    private static Boolean toBoolean(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return "Y".equalsIgnoreCase(value.trim()) || "true".equalsIgnoreCase(value.trim());
    }

    public record AvailabilityResult(
            Boolean hasBook,
            Boolean loanAvailable,
            String message,
            boolean success
    ) {
        public static AvailabilityResult failed(String message) {
            return new AvailabilityResult(null, null, message, false);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record BookExistResponse(BookExistEnvelope response) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record BookExistEnvelope(BookExistResult result) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record BookExistResult(String hasBook, String loanAvailable) {
    }
}
