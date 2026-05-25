package com.taeo.bookcuration.library.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.config.Data4LibraryProperties;
import com.taeo.bookcuration.library.dto.LibraryDtos.LibrarySyncResponse;
import com.taeo.bookcuration.library.repository.LibraryJdbcRepository;
import com.taeo.bookcuration.library.repository.LibraryJdbcRepository.LibraryRow;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Service
@RequiredArgsConstructor
public class LibrarySyncService {

    private final Data4LibraryProperties properties;
    private final LibraryJdbcRepository libraryJdbcRepository;
    private final ObjectMapper objectMapper;
    private final RestClient.Builder restClientBuilder;

    public LibrarySyncResponse syncLibraries() {
        validateProperties();

        int pageNo = 1;
        int pageSize = properties.safePageSize();

        int totalCount = 0;
        int savedCount = 0;
        int pageCount = 0;

        while (true) {
            JsonNode root = requestLibraryPage(pageNo, pageSize);
            JsonNode response = root.path("response");

            if (pageNo == 1) {
                totalCount = response.path("numFound").asInt(0);
            }

            JsonNode libs = response.path("libs");
            if (!libs.isArray() || libs.isEmpty()) {
                break;
            }

            List<LibraryRow> rows = parseLibraries(libs);
            libraryJdbcRepository.upsertAll(rows);

            savedCount += rows.size();
            pageCount++;

            if (totalCount > 0 && savedCount >= totalCount) {
                break;
            }

            pageNo++;
        }

        return new LibrarySyncResponse(totalCount, savedCount, pageCount);
    }

    private JsonNode requestLibraryPage(int pageNo, int pageSize) {
        RestClient restClient = restClientBuilder
                .baseUrl(properties.baseUrl())
                .build();

        return restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/api/libSrch")
                        .queryParam("authKey", properties.authKey())
                        .queryParam("pageNo", pageNo)
                        .queryParam("pageSize", pageSize)
                        .queryParam("format", "json")
                        .build()
                )
                .retrieve()
                .body(JsonNode.class);
    }

    private List<LibraryRow> parseLibraries(JsonNode libs) {
        List<LibraryRow> rows = new ArrayList<>();

        for (JsonNode wrapper : libs) {
            JsonNode lib = wrapper.path("lib");

            String libCode = text(lib, "libCode");
            String libName = text(lib, "libName");

            if (isBlank(libCode) || isBlank(libName)) {
                continue;
            }

            rows.add(new LibraryRow(
                    libCode,
                    libName,
                    text(lib, "address"),
                    firstText(lib, "operatingTime", "operationTime"),
                    text(lib, "closed"),
                    integer(lib, "BookCount"),
                    decimal(lib, "latitude"),
                    decimal(lib, "longitude"),
                    toRawJson(lib)
            ));
        }

        return rows;
    }

    private String toRawJson(JsonNode node) {
        try {
            return objectMapper.writeValueAsString(node);
        } catch (Exception e) {
            return "{}";
        }
    }

    private String text(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || value.isNull()) {
            return null;
        }

        String text = value.asText();
        return isBlank(text) ? null : text;
    }

    private String firstText(JsonNode node, String... fieldNames) {
        for (String fieldName : fieldNames) {
            String value = text(node, fieldName);
            if (!isBlank(value)) {
                return value;
            }
        }
        return null;
    }

    private Integer integer(JsonNode node, String fieldName) {
        String value = text(node, fieldName);
        if (isBlank(value)) {
            return null;
        }

        try {
            return Integer.parseInt(value.replace(",", ""));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private BigDecimal decimal(JsonNode node, String fieldName) {
        String value = text(node, fieldName);
        if (isBlank(value)) {
            return null;
        }

        try {
            return new BigDecimal(value);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private void validateProperties() {
        if (isBlank(properties.baseUrl())) {
            throw new IllegalStateException("data4library.base-url 설정이 필요합니다.");
        }

        if (isBlank(properties.authKey())) {
            throw new IllegalStateException("DATA4LIBRARY_AUTH_KEY 설정이 필요합니다.");
        }
    }
}
