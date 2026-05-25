
/**
 * 구글 로그인 버튼 컴포넌트
 *
 * 역할:
 * - 구글 소셜 로그인 시작 버튼 UI를 담당한다.
 * - 실제 OAuth 이동 처리는 부모로부터 전달받은 onClick에서 수행한다.
 *
 * 구현 이유:
 * - PNG 이미지 비율 문제를 피하기 위해 아이콘 + 텍스트 조합으로 직접 버튼을 구성한다.
 * - shadcn 기본 버튼 높이와 맞추기 위해 h-10을 사용한다.
 */

import { cn } from "@/lib/utils";

type Props = {
  onClick: () => void;
  disabled?: boolean;
};

const GoogleIcon = () => {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="h-4 w-4 shrink-0"
    >
      <path
        fill="#EA4335"
        d="M12 10.2v3.9h5.5c-.2 1.3-.8 2.4-1.7 3.2l2.8 2.2c1.7-1.5 2.7-3.9 2.7-6.8 0-.7-.1-1.4-.2-2H12z"
      />
      <path
        fill="#34A853"
        d="M12 21c2.4 0 4.5-.8 6-2.2l-2.8-2.2c-.8.5-1.8.9-3.2.9-2.5 0-4.6-1.7-5.3-4l-2.9 2.3C5.3 18.9 8.4 21 12 21z"
      />
      <path
        fill="#4A90E2"
        d="M6.7 13.5c-.2-.6-.3-1.1-.3-1.7s.1-1.2.3-1.7L3.8 7.8C3.3 8.9 3 10 3 11.8s.3 2.9.8 4l2.9-2.3z"
      />
      <path
        fill="#FBBC05"
        d="M12 6.1c1.4 0 2.6.5 3.6 1.4l2.6-2.6C16.5 3.3 14.4 2.5 12 2.5c-3.6 0-6.7 2.1-8.2 5.3l2.9 2.3c.7-2.3 2.8-4 5.3-4z"
      />
    </svg>
  );
};

const GoogleLoginButton = ({ onClick, disabled = false }: Props) => {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label="구글 로그인"
      className={cn(
        "flex h-10 w-full items-center justify-center gap-2 rounded-md border border-input bg-white px-4 text-sm font-medium text-slate-700",
        "transition hover:bg-slate-50 hover:shadow-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-60"
      )}
    >
      <GoogleIcon />
      <span>Google로 로그인</span>
    </button>
  );
};

export default GoogleLoginButton;
