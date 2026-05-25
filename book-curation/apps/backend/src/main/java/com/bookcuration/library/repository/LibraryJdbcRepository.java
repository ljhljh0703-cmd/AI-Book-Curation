package com.taeo.bookcuration.library.repository;

import com.taeo.bookcuration.library.dto.LibraryDtos.LibraryPageResponse;
import com.taeo.bookcuration.library.dto.LibraryDtos.LibrarySearchResponse;
import com.taeo.bookcuration.library.dto.LibraryDtos.NearbyLibraryResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Types;
import java.util.List;
import java.util.Optional;

@Repository
@RequiredArgsConstructor
public class LibraryJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    public void upsertAll(List<LibraryRow> libraries) {
        String sql = """
                INSERT INTO book.libraries (
                    lib_code,
                    lib_name,
                    address,
                    operating_time,
                    closed,
                    book_count,
                    latitude,
                    longitude,
                    raw_json,
                    synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), now())
                ON CONFLICT (lib_code) DO UPDATE SET
                    lib_name = EXCLUDED.lib_name,
                    address = EXCLUDED.address,
                    operating_time = EXCLUDED.operating_time,
                    closed = EXCLUDED.closed,
                    book_count = EXCLUDED.book_count,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    raw_json = EXCLUDED.raw_json,
                    synced_at = now(),
                    updated_at = now()
                """;

        jdbcTemplate.batchUpdate(sql, libraries, 100, (PreparedStatement ps, LibraryRow row) -> {
            ps.setString(1, row.libCode());
            ps.setString(2, row.libName());
            ps.setString(3, row.address());
            ps.setString(4, row.operatingTime());
            ps.setString(5, row.closed());

            if (row.bookCount() == null) {
                ps.setNull(6, Types.INTEGER);
            } else {
                ps.setInt(6, row.bookCount());
            }

            if (row.latitude() == null) {
                ps.setNull(7, Types.NUMERIC);
            } else {
                ps.setBigDecimal(7, row.latitude());
            }

            if (row.longitude() == null) {
                ps.setNull(8, Types.NUMERIC);
            } else {
                ps.setBigDecimal(8, row.longitude());
            }

            ps.setString(9, row.rawJson());
        });
    }

    public boolean existsByLibCode(String libCode) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM book.libraries WHERE lib_code = ?",
                Integer.class,
                libCode
        );
        return count != null && count > 0;
    }


    public Optional<LibrarySummary> findSummaryByLibCode(String libCode) {
        String sql = """
                SELECT lib_code, lib_name, address, latitude, longitude
                FROM book.libraries
                WHERE lib_code = ?
                """;

        List<LibrarySummary> rows = jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new LibrarySummary(
                        rs.getString("lib_code"),
                        rs.getString("lib_name"),
                        rs.getString("address"),
                        rs.getBigDecimal("latitude"),
                        rs.getBigDecimal("longitude")
                ),
                libCode
        );
        return rows.stream().findFirst();
    }

    public LibraryPageResponse<NearbyLibraryResponse> findNearby(
            double latitude,
            double longitude,
            int radiusMeters,
            int page,
            int size
    ) {
        String countSql = """
                SELECT COUNT(*)
                FROM book.libraries
                WHERE location IS NOT NULL
                  AND ST_DWithin(
                        location,
                        ST_SetSRID(ST_MakePoint(?, ?), 4326)::GEOGRAPHY,
                        ?
                  )
                """;

        Long totalElements = jdbcTemplate.queryForObject(
                countSql,
                Long.class,
                longitude,
                latitude,
                radiusMeters
        );

        String sql = """
                SELECT
                    lib_code,
                    lib_name,
                    address,
                    latitude,
                    longitude,
                    ROUND(
                        ST_Distance(
                            location,
                            ST_SetSRID(ST_MakePoint(?, ?), 4326)::GEOGRAPHY
                        )::NUMERIC,
                        2
                    ) AS distance_meters
                FROM book.libraries
                WHERE location IS NOT NULL
                  AND ST_DWithin(
                        location,
                        ST_SetSRID(ST_MakePoint(?, ?), 4326)::GEOGRAPHY,
                        ?
                  )
                ORDER BY distance_meters ASC
                LIMIT ? OFFSET ?
                """;

        List<NearbyLibraryResponse> content = jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new NearbyLibraryResponse(
                        rs.getString("lib_code"),
                        rs.getString("lib_name"),
                        rs.getString("address"),
                        rs.getBigDecimal("latitude"),
                        rs.getBigDecimal("longitude"),
                        rs.getBigDecimal("distance_meters")
                ),
                longitude,
                latitude,
                longitude,
                latitude,
                radiusMeters,
                size,
                (long) page * size
        );

        return LibraryPageResponse.of(content, page, size, totalElements == null ? 0 : totalElements);
    }

    public LibraryPageResponse<LibrarySearchResponse> searchByKeyword(String keyword, int page, int size) {
        String normalizedKeyword = keyword == null ? "" : keyword.trim().toLowerCase();
        if (normalizedKeyword.length() < 2) {
            return LibraryPageResponse.empty(page, size);
        }

        String likeKeyword = "%" + normalizedKeyword + "%";
        String countSql = """
                SELECT COUNT(*)
                FROM book.libraries
                WHERE lower(coalesce(lib_name, '')) LIKE ?
                   OR lower(coalesce(address, '')) LIKE ?
                """;

        Long totalElements = jdbcTemplate.queryForObject(
                countSql,
                Long.class,
                likeKeyword,
                likeKeyword
        );

        String sql = """
                SELECT
                    lib_code,
                    lib_name,
                    address,
                    latitude,
                    longitude
                FROM book.libraries
                WHERE lower(coalesce(lib_name, '')) LIKE ?
                   OR lower(coalesce(address, '')) LIKE ?
                ORDER BY
                    CASE WHEN lower(coalesce(lib_name, '')) LIKE ? THEN 0 ELSE 1 END,
                    lib_name ASC,
                    lib_code ASC
                LIMIT ? OFFSET ?
                """;

        List<LibrarySearchResponse> content = jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new LibrarySearchResponse(
                        rs.getString("lib_code"),
                        rs.getString("lib_name"),
                        rs.getString("address"),
                        rs.getBigDecimal("latitude"),
                        rs.getBigDecimal("longitude")
                ),
                // 수정 포인트: 일반 사용자용 도서관 검색에서는 내부 식별자인 lib_code를 검색 조건에서 제외합니다.
                likeKeyword,
                likeKeyword,
                normalizedKeyword + "%",
                size,
                (long) page * size
        );

        return LibraryPageResponse.of(content, page, size, totalElements == null ? 0 : totalElements);
    }

    public record LibrarySummary(
            String libCode,
            String libName,
            String address,
            BigDecimal latitude,
            BigDecimal longitude
    ) {
    }

    public record LibraryRow(
            String libCode,
            String libName,
            String address,
            String operatingTime,
            String closed,
            Integer bookCount,
            BigDecimal latitude,
            BigDecimal longitude,
            String rawJson
    ) {
    }
}
