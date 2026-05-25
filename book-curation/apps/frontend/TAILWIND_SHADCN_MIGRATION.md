# Tailwind + shadcn/ui 변경 내역

## 적용 내용

- `bootstrap`, `react-bootstrap` 의존성을 제거했습니다.
- Tailwind CSS v4의 Vite 플러그인(`@tailwindcss/vite`)을 적용했습니다.
- shadcn/ui 방식의 기본 컴포넌트를 추가했습니다.
  - `src/components/ui/button.tsx`
  - `src/components/ui/card.tsx`
  - `src/components/ui/input.tsx`
  - `src/components/ui/label.tsx`
  - `src/components/ui/alert.tsx`
  - `src/components/ui/badge.tsx`
- `@/` import alias를 추가했습니다.
- Navbar, Home, Login, Signup, OAuthSuccess, Profile 화면을 Tailwind + shadcn/ui 스타일로 변경했습니다.
- 기존 인증 API 로직은 유지했습니다.

## 실행 방법

```bash
npm install
npm run dev
```

빌드 확인:

```bash
npm run build
```

## 참고

`package-lock.json`은 기존 Bootstrap 의존성과 맞물려 있어서 제거했습니다. 새 의존성 기준으로 `npm install` 실행 시 다시 생성됩니다.
