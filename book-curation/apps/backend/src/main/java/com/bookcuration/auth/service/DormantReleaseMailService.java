package com.taeo.bookcuration.auth.service;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

@Service
@RequiredArgsConstructor
public class DormantReleaseMailService {

    private static final DateTimeFormatter EXPIRES_AT_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    private final JavaMailSender javaMailSender;

    @Value("${spring.mail.host:}")
    private String mailHost;

    @Value("${spring.mail.username:}")
    private String mailUsername;

    @Value("${spring.mail.password:}")
    private String mailPassword;

    @Value("${app.auth.dormant-release.mail-from:}")
    private String mailFrom;

    @Value("${app.auth.dormant-release.mail-subject:[Bookemon] 휴면 해제 인증번호}")
    private String mailSubject;

    public void sendDormantReleaseCode(String toEmail, String nickname, String code, OffsetDateTime expiresAt) {
        validateMailConfiguration();

        SimpleMailMessage message = new SimpleMailMessage();
        if (mailFrom != null && !mailFrom.isBlank()) {
            message.setFrom(mailFrom);
        }
        message.setTo(toEmail);
        message.setSubject(mailSubject);
        message.setText(buildMailBody(nickname, code, expiresAt));

        try {
            javaMailSender.send(message);
        } catch (MailException e) {
            throw new IllegalStateException("휴면 해제 인증번호 메일 전송에 실패했습니다. SMTP 계정/비밀번호와 발신 주소 설정을 확인해 주세요.", e);
        }
    }

    private void validateMailConfiguration() {
        if (mailHost == null || mailHost.isBlank()) {
            throw new IllegalStateException("메일 서버 설정이 없어 휴면 해제 인증번호 메일을 보낼 수 없습니다. MAIL_HOST 환경변수를 설정해 주세요.");
        }
        if (mailUsername == null || mailUsername.isBlank()) {
            throw new IllegalStateException("메일 계정 설정이 없어 휴면 해제 인증번호 메일을 보낼 수 없습니다. MAIL_USERNAME 환경변수를 설정해 주세요.");
        }
        if (mailPassword == null || mailPassword.isBlank()) {
            throw new IllegalStateException("메일 비밀번호 설정이 없어 휴면 해제 인증번호 메일을 보낼 수 없습니다. MAIL_PASSWORD 환경변수를 설정해 주세요.");
        }
    }

    private String buildMailBody(String nickname, String code, OffsetDateTime expiresAt) {
        String safeNickname = (nickname == null || nickname.isBlank()) ? "회원" : nickname.trim();
        String expiresAtText = expiresAt
                .atZoneSameInstant(ZoneId.of("Asia/Seoul"))
                .format(EXPIRES_AT_FORMATTER);

        return "안녕하세요, " + safeNickname + "님.\n\n"
                + "Bookemon 휴면 해제 인증번호를 안내드립니다.\n\n"
                + "인증번호: " + code + "\n"
                + "유효시간: " + expiresAtText + " (KST)\n\n"
                + "본인이 요청하지 않았다면 이 메일을 무시해 주세요.";
    }
}
