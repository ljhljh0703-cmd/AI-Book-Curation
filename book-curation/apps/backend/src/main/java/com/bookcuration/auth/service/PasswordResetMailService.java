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
public class PasswordResetMailService {

    private static final DateTimeFormatter EXPIRES_AT_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    private final JavaMailSender javaMailSender;

    @Value("${spring.mail.host:}")
    private String mailHost;

    @Value("${spring.mail.username:}")
    private String mailUsername;

    @Value("${spring.mail.password:}")
    private String mailPassword;

    @Value("${app.auth.password-reset.mail-from:}")
    private String mailFrom;

    @Value("${app.auth.password-reset.mail-subject:[Bookemon] 비밀번호 재설정 인증번호}")
    private String mailSubject;

    public void sendPasswordResetCode(String toEmail, String nickname, String code, OffsetDateTime expiresAt) {
        validateMailConfiguration();

        SimpleMailMessage message = new SimpleMailMessage();
        String fromAddress = firstNonBlank(mailFrom, mailUsername);
        if (fromAddress != null) {
            // 수정 포인트: PASSWORD_RESET_MAIL_FROM이 비어 있어도 SMTP 계정 주소를 발신자로 사용해 메일 서버의 발신자 검증 실패 가능성을 줄입니다.
            message.setFrom(fromAddress);
        }
        message.setTo(toEmail);
        message.setSubject(mailSubject);
        message.setText(buildMailBody(nickname, code, expiresAt));

        try {
            javaMailSender.send(message);
        } catch (MailException e) {
            throw new IllegalStateException("인증번호 메일 전송에 실패했습니다. 메일 계정 또는 발신 주소 설정을 확인해 주세요.", e);
        }
    }

    private void validateMailConfiguration() {
        if (mailHost == null || mailHost.isBlank()) {
            throw new IllegalStateException("인증번호 메일 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.");
        }
        if (mailUsername == null || mailUsername.isBlank()) {
            throw new IllegalStateException("인증번호 메일 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.");
        }
        if (mailPassword == null || mailPassword.isBlank()) {
            throw new IllegalStateException("인증번호 메일 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.");
        }
    }

    private static String firstNonBlank(String first, String second) {
        if (first != null && !first.isBlank()) {
            return first.trim();
        }
        if (second != null && !second.isBlank()) {
            return second.trim();
        }
        return null;
    }

    private String buildMailBody(String nickname, String code, OffsetDateTime expiresAt) {
        String safeNickname = (nickname == null || nickname.isBlank()) ? "회원" : nickname.trim();
        String expiresAtText = expiresAt
                .atZoneSameInstant(ZoneId.of("Asia/Seoul"))
                .format(EXPIRES_AT_FORMATTER);

        return "안녕하세요, " + safeNickname + "님.\n\n"
        + "Bookemon 비밀번호 재설정 인증번호를 안내드립니다.\n\n"
        + "인증번호: " + code + "\n"
        + "유효시간: " + expiresAtText + " (KST)\n\n"
        + "본인이 요청하지 않았다면 이 메일을 무시해 주세요.";
    }
}
