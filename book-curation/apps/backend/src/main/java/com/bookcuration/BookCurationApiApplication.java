package com.taeo.bookcuration;

import com.taeo.bookcuration.config.AiServerProperties;
import com.taeo.bookcuration.config.AladinProperties;
import com.taeo.bookcuration.config.CorsProperties;
import com.taeo.bookcuration.config.Data4LibraryProperties;
import com.taeo.bookcuration.config.RedisProperties;
import com.taeo.bookcuration.config.QueryEvaluationRunnerProperties;
import com.taeo.bookcuration.recommendation.lightfm.LightFmTrainingProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
@EnableConfigurationProperties({
        AiServerProperties.class, // 수정 포인트: backend에서 ai-server 내부 API 호출 설정을 환경변수로 주입받습니다.
        AladinProperties.class, // 수정 포인트: 알라딘 TTBKey와 검색 API 설정을 환경변수 기반으로 주입받습니다.
        CorsProperties.class,
        Data4LibraryProperties.class,
        LightFmTrainingProperties.class,
        RedisProperties.class,
        QueryEvaluationRunnerProperties.class
})
public class BookCurationApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookCurationApiApplication.class, args);
    }
}
