/**
 * 마이페이지 정보 표시 공통 컴포넌트.
 * 수정 포인트: 단순 입력 박스처럼 보이지 않도록 카드형 정보 타일 UI로 변경했다.
 */

import type { ReactNode } from "react";

type Props = {
  label: string;
  value: ReactNode;
};

const ProfileInfoRow = ({ label, value }: Props) => {
  return (
    <div className="group rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </span>
      <div className="mt-2 min-h-6 break-all text-sm font-bold text-slate-950">
        {value}
      </div>
    </div>
  );
};

export default ProfileInfoRow;
