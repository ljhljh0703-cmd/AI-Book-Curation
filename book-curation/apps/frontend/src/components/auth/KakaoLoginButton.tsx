/**
 * 카카오 로그인 버튼 컴포넌트
 *
 * 역할:
 * - 카카오 소셜 로그인 시작 버튼 UI를 담당한다.
 */

import { cn } from "@/lib/utils";

type Props = {
  onClick: () => void;
  disabled?: boolean;
};

const KakaoIcon = () => {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="h-4 w-4 shrink-0"
    >
      <path
        fill="currentColor"
        d="M12 4C7 4 3 7.1 3 11c0 2.4 1.5 4.5 3.8 5.8L5.9 20.9c-.1.4.3.7.7.5l4.8-3.1c.2 0 .4 0 .6 0 5 0 9-3.1 9-7s-4-7.3-9-7.3z"
      />
    </svg>
  );
};

const KakaoLoginButton = ({ onClick, disabled = false }: Props) => {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label="카카오 로그인"
      className={cn(
        "flex h-10 w-full items-center justify-center gap-2 rounded-md border border-[#E2C400] bg-[#FEE500] px-4 text-sm font-medium text-[#191919]",
        "transition hover:brightness-95 hover:shadow-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-60"
      )}
    >
      <KakaoIcon />
      <span>카카오로 로그인</span>
    </button>
  );
};

export default KakaoLoginButton;