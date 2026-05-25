import {
  Activity,
  BookOpenCheck,
  BrainCircuit,
  Clock3,
  DatabaseZap,
  ListChecks,
  Sparkles,
  TableProperties,
} from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

type AdminLayoutProps = {
  title: string;
  description: string;
  children: ReactNode;
};

const adminMenuItems = [
  {
    to: "/admin/monitoring",
    label: "모니터링",
    icon: Activity,
  },
  {
    to: "/admin/recommendation-model",
    label: "추천 모델 설정",
    icon: BrainCircuit,
  },
  {
    to: "/admin/evaluation",
    label: "평가 관리",
    icon: TableProperties,
  },
  {
    to: "/admin/review-policy",
    label: "리뷰 정책 설정",
    icon: Clock3,
  },
  {
    to: "/admin/libraries",
    label: "도서관 동기화",
    icon: DatabaseZap,
  },
  {
    to: "/admin/onboarding-options",
    label: "온보딩 항목 관리",
    icon: ListChecks,
  },
  {
    to: "/admin/characters",
    label: "캐릭터 설정",
    icon: Sparkles,
  },
];

const AdminLayout = ({ title, description, children }: AdminLayoutProps) => {
  return (
    <main className="mx-auto min-h-[calc(100vh-4rem)] w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="rounded-2xl border bg-card p-4 shadow-sm lg:sticky lg:top-20 lg:h-fit">
          <div className="mb-5 flex items-center gap-2 rounded-xl bg-muted/50 px-3 py-3">
            <BookOpenCheck className="size-5 text-primary" />
            <div>
              <p className="text-sm font-semibold">관리자 메뉴</p>
              <p className="text-xs text-muted-foreground">서비스 설정 관리</p>
            </div>
          </div>

          <nav className="space-y-1">
            {adminMenuItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )
                  }
                >
                  <Icon className="size-4" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <section className="min-w-0 space-y-5">
          <header className="rounded-2xl border bg-card p-6 shadow-sm">
            <p className="text-sm font-medium text-primary">관리자 전용</p>
            <h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">
              {title}
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {description}
            </p>
          </header>

          {children}
        </section>
      </div>
    </main>
  );
};

export default AdminLayout;
