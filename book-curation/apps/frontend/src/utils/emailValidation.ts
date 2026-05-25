const EMAIL_PATTERN = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;

export const ALLOWED_SIGNUP_EMAIL_DOMAINS = [
  "gmail.com",
  "nate.com",
  "kakao.com",
  "naver.com",
  "daum.net",
] as const;

const ALLOWED_SIGNUP_EMAIL_DOMAIN_SET = new Set<string>(ALLOWED_SIGNUP_EMAIL_DOMAINS);

export const validateSignupEmail = (email: string): string => {
  const trimmed = email.trim().toLowerCase();

  if (!trimmed) {
    return "이메일을 입력해 주세요.";
  }

  if (trimmed.length > 254) {
    return "이메일은 254자 이하로 입력해 주세요.";
  }

  const [localPart, domainPart] = trimmed.split("@");

  if (
    !EMAIL_PATTERN.test(trimmed) ||
    !localPart ||
    !domainPart ||
    localPart.length > 64 ||
    localPart.startsWith(".") ||
    localPart.endsWith(".") ||
    localPart.includes("..") ||
    domainPart.includes("..")
  ) {
    return "올바른 이메일 형식으로 입력해 주세요.";
  }

  if (!ALLOWED_SIGNUP_EMAIL_DOMAIN_SET.has(domainPart)) {
    // 수정 포인트: 실제 이메일 인증은 하지 않되, 가입 가능한 이메일 도메인을 서비스 정책상 허용 목록으로 제한합니다.
    return "가입 가능한 이메일 도메인은 gmail.com, nate.com, kakao.com, naver.com, daum.net입니다.";
  }

  return "";
};
